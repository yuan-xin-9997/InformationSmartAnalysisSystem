## Context

推送邮件链路现状（`services/push/`）：

- `render.py`：`PushEvent`（扁平 dataclass）-> `render_events(rule_name, events) -> (subject, html, text)`。HTML 正文把每条事件渲染为卡片（头部 + 文件/文章信息 + Markdown→HTML），**不含图表**。`mistune(escape=True)` 渲染 Markdown。
- `attachments.py`：`collect_attachments(db, results) -> list[Attachment]`，从 `InfoItemFigure.storage_path` 读图表字节、校验 `is_relative_to(figures_dir)`、超 10MB/越界/不存在则跳过记日志，返回**附件**（`Attachment(filename, mime, data)`）。原文件仅 `local_folder`。
- `email_channel.py`：`send(cfg, recipients, subject, html, text, attachments=None)`。无附件用 `multipart/alternative`；有附件用 `multipart/mixed`(alternative + 附件 `Content-Disposition: attachment`)。**无内联图片**。
- `service.py`：`run_push` 按批（`max_events_per_email`，默认 50）渲染+收集附件+发送，每批成功推进水位线；`_log_run` 写一条 `PushRun`（`status/event_count/error/recipients/时间`，**无邮件内容**）。多批 = 多封邮件，但只写 1 条 `PushRun`。
- `models/push.py`：`PushRun` 无内容/主题/附件字段。
- API：`GET /{task_id}/push/runs` 返回 `list[PushRunOut]`（无内容）；前端 `AnalysisTasks.vue:274-301` 推送历史仅卡片，无预览。

排查结论（邮件正文无图表）：图表按规格是**附件**（`event-push`「邮件附件」Requirement），非正文内嵌；`enhance-push-email-content` 把「正文内嵌图表」列为 Non-Goal（理由：图表服务接口需鉴权、邮件外部无法访问）。但该顾虑对 **CID 内嵌**不成立--附件实现已从磁盘读到图表字节，可直接内嵌进 HTML 正文，邮件客户端无需回访鉴权接口。图表抽取代码（`extract_figures`/`_figures_pdf`/`_figures_docx`）在 8/6 OCR 重构中未受影响，`figures_dir` 默认 `data_dir/figures`，附件链路本身正常。

约束：CLAUDE.md（不硬编码环境信息、时间北京时间、优先 SQLite/Python、`data` 不入 `.gitignore`）；无新第三方依赖（`email.mime` 标准库）；邮件 HTML 安全（`mistune escape=True` 已转义原生 HTML）。

## Goals / Non-Goals

**Goals:**
- `per_item` 事件邮件正文以 CID 内嵌图表（邮件客户端直接可见），图表同时保留为附件。
- 推送历史留存实际发送的邮件主题/HTML/附件清单；前端可预览（含内嵌图表）。
- 多批邮件内容可合并预览。
- 复用既有图表字节读取与路径校验，不新增读取路径。

**Non-Goals:**
- 不改推送规则、触发方式、增量水位线、SMTP 配置逻辑。
- 不改图表抽取链路（`info_source`）。
- 不做预览内容的全文检索/导出。
- 不改 `aggregate` 事件（无图表、无附件）。
- 不为预览引入新前端依赖（用 `iframe srcdoc`）。

## Decisions

### 决策 1：`PushRun` 新增 `subject`/`email_html`/`attachment_summary` 列
`PushRun` 增 3 列：`subject: str | None`、`email_html: Text | None`、`attachment_summary: JSON | None`（`[{filename, kind, skipped?}]`）。`email_html` 为**浏览器可渲染**版本（见决策 4）。未发送邮件的记录（`no_new`、发送前 `failed`）这 3 列为 `None`。`has_preview` 由 `email_html IS NOT NULL` 派生（API 层计算，不入库）。
**理由**：推送历史是 1:1 的回看入口，留存内容使排查无须翻日志；`attachment_summary` 体积小可直接随列表返回，`email_html` 体积大按需单独取。
**备选**：把 `email_html` 直接放进 `PushRunOut` 列表响应--否（HTML 可达数百 KB~MB，列表加载过重）。

### 决策 2：图表字节「一次读取、两用」（内联 + 附件）
重构 `attachments.py` 为 `collect_push_media(db, results) -> (attachments, inline_figures)`：
- `attachments: list[Attachment]`：原文件（`local_folder`）+ 图表附件（与现状一致）。
- `inline_figures: list[InlineImage]`：`InlineImage(cid, filename, mime, data, item_id)`，源自**同一批** `InfoItemFigure` 查询与同一次字节读取，每个图表分配唯一 CID。
`service.py` 把 `item_id -> [InlineImage]` 传给 `_to_push_event`，填入 `PushEvent.figures: list[FigureRef]`（`FigureRef(cid, mime)`，**不存字节**，渲染只需 cid）。
**理由**：内联与附件同源同字节，避免重复读盘与不一致；`PushEvent` 保持轻量（不携带字节），字节由 `inline_figures` 统一传给 channel。
**备选**：`PushEvent` 直接携带字节--否（渲染层无需字节，且 `render.py` 与 ORM 解耦的设计原则要求渲染层不碰字节）。

### 决策 3：`render_events` 返回内联图片清单
`render_events(rule_name, events) -> (subject, html, text, inline_images)`：
- `html` 在每条 `per_item` 事件的分析结果后插入 `<img src="cid:{cid}" .../>`（来自 `event.figures`）；无图表则不插。
- `inline_images` = 跨事件聚合的 `[{cid, mime, data, filename}]`（来自 `PushEvent.figures` + service 注入的字节），供 channel 构造内联 MIME 部分。
**理由**：CID 在渲染时确定，channel 据此匹配 `Content-ID`；聚合返回避免 service 再拼。
**备选**：service 自己拼 `inline_images`--否（render 已知 cid 顺序，聚合更自然）。

### 决策 4：邮件用 `cid:`，预览存 `data:` 版本（浏览器可渲染）
浏览器 `<iframe srcdoc>` **无法解析 `cid:` URL**（CID 仅邮件客户端识别）。故：
- **邮件**：`html` 用 `cid:` 引用；`email_channel.send` 接收 `inline_images`，构造内联 MIME 部分（`Content-Disposition: inline` + `Content-ID: <cid>`）。
- **预览留存**：service 调 `_cid_to_data_url(html, inline_images)` 把每个 `cid:{cid}` 替换为 `data:{mime};base64,{data}`，生成自包含 HTML 存入 `PushRun.email_html`。预览接口直接返回该 HTML，前端 `iframe srcdoc` 即可显示图表，**无须运行时回读磁盘**。
**理由**：邮件客户端要 `cid:`；浏览器要 `data:`。两版同源同字节，发送时一次性生成 `data:` 版留存，预览不依赖图表文件是否仍在磁盘（即使后续重新抽取/删除图表，历史预览仍完整）。
**备选**：预览接口运行时把 `cid:` 替换为 `data:`（回读 `InfoItemFigure`）--否（图表可能被重新抽取致 `storage_path` 变更/删除，预览会断图）。
**权衡**：`email_html` 含 base64 图表，体积随图表数增大（单图受 10MB 上限约束）。个人系统推送量有限，可接受；如需控制可后续加「预览留存天数清理」。

### 决策 5：MIME 结构 `multipart/mixed > related > alternative + 内联图片` + 附件
有内联图片 + 附件时：
```
multipart/mixed
├─ multipart/related
│  ├─ multipart/alternative  (text/plain + text/html[cid:])
│  └─ inline image parts (Content-Disposition: inline; Content-ID: <cid>)  ×N
└─ attachment parts (Content-Disposition: attachment)  ×M
```
无内联图片时退化（`related` 仅含 alternative，或直接 `mixed`>alternative+附件，与现状兼容）。无附件无内联时保持 `alternative`。
**理由**：`related` 把 HTML 与其引用的内联图片绑定（RFC 2387），是内联图邮件标准结构；附件独立在 `mixed` 顶层。标准库 `email.mime` 即可构造。
**备选**：把内联图片也放 `mixed` 顶层--否（部分客户端不把顶层 inline 部分关联到 HTML，图不显示）。

### 决策 6：多批邮件合并留存
`run_push` 多批时，每批产生一组 `(subject_i, html_i, inline_images_i, attachments_i)`。留存策略：把各批 `html`（`data:` 版）按顺序拼接（每批前插一个分隔标题「第 i 封 / 共 N 封」），合并存入单条 `PushRun.email_html`；`subject` 存首封主题（或 `主题(共N封)`）；`attachment_summary` 合并各批。预览展示合并内容。
**理由**：1 条 `PushRun` = 1 次推送执行，合并留存与「按执行回看」语义一致；避免引入「推送邮件子表」。
**备选**：新增 `PushEmail` 子表每封一行--否（过度设计，多批场景少）。

### 决策 7：预览 API 与权限
新增 `GET /api/analysis-tasks/{task_id}/push/runs/{run_id}/preview` -> `{subject, html, attachments}`（`attachments` 即 `attachment_summary`）。`require_page("analysis_tasks")` 保护；`email_html IS NULL` 返回 404。`PushRunOut` 增 `has_preview: bool` 与 `attachment_summary: list`（小字段随列表返回，决定是否显示「预览」按钮）。
**理由**：大字段按需取；列表只需知道能否预览 + 附件摘要。
**备选**：预览也走 `GET /{task_id}/push/runs`（列表带 html）--否（体积）。

### 决策 8：前端预览弹层用 `iframe srcdoc` + sandbox
`AnalysisTasks.vue` 推送历史卡片：`run.has_preview` 时显示「预览」按钮；点击调预览接口，弹层内 `<iframe :srcdoc="html" sandbox="allow-same-origin" referrerpolicy="no-referrer">` 渲染。`sandbox` 不加 `allow-scripts`（双重防御：`mistune escape=True` 已转义脚本，sandbox 再禁脚本执行）。
**理由**：`srcdoc` 渲染自包含 HTML（含 `data:` 图）；`sandbox` 防御性禁脚本；无新依赖。
**备选**：`v-html` 直接注入--否（样式污染 + 脚本风险高于 iframe 隔离）。

## Risks / Trade-offs

- **`email_html` 体积增长**（含 base64 图表）-> 单图受 10MB 上限；个人系统量小可接受；后续可加「预览留存 N 天清理」或仅留存最近 K 条。
- **邮件客户端 CID 兼容性**（QQ/163 网页版可能剥离内联图）-> 用标准 `related` 结构最大化兼容；即便个别客户端剥离内联，图表仍作为附件可下载，不丢信息。
- **图表既内联又附件 = 字节双发**（邮件体积约增图表字节量）-> 用户已确认接受（选项「正文内嵌+保留附件」）；典型 PDF 图表数有限。
- **历史预览与实际邮件非字节级一致**（邮件 `cid:`、留存 `data:`）-> 内容等价；留存版专为浏览器预览，符合「预览」语义。
- **多批合并 HTML 过长** -> 受 `max_events_per_email` 与图表 10MB 上限约束；极端情况预览渲染慢但可用。

## Migration Plan

1. **模型/迁移**：`models/push.py` `PushRun` 增 3 列；`core/database.py` 启动时增量 `ALTER TABLE push_runs ADD COLUMN ...`（SQLite 兼容，IF NOT EXISTS 语义）。
2. **附件层**：`attachments.py` 重构为 `collect_push_media` 返回 `(attachments, inline_figures)`；`InlineImage`/`FigureRef` dataclass。
3. **渲染层**：`render.py` `PushEvent` 增 `figures`；`render_events` 插 `<img src="cid:">` 并返回 `inline_images`。
4. **渠道层**：`email_channel.py` `send` 增 `inline_images` 参数，构造 `related>alternative+inline` + 附件 MIME。
5. **服务层**：`service.py` `run_push` 收集每批 `subject/html/inline_images/attachments`；`_cid_to_data_url` 生成预览 HTML；多批合并；`_log_run` 写入新列与 `attachment_summary`。
6. **API/Schema**：`schemas/push.py` `PushRunOut` 增 `has_preview`/`attachment_summary`；`api/analysis_tasks.py` 增 `GET .../runs/{run_id}/preview`。
7. **前端**：`api/push.ts` 增预览接口与 `has_preview`/`attachment_summary` 字段；`AnalysisTasks.vue` 卡片「预览」按钮 + `iframe srcdoc` 弹层。
8. **测试**：扩展 `test_push_render.py`（cid 插入/无图不占位/aggregate 无图）、`test_push_attachments.py`（`collect_push_media` 返回内联+附件双份）、`test_push_channel.py`（MIME 结构含 inline `Content-ID`）、`test_push_service.py`（`PushRun` 留存 `email_html`/多批合并）、`test_push_api.py`（预览接口 + 权限 403 + 404）。
9. **文档**：需求规格说明书、设计说明书、README（推送历史预览 + 正文内嵌图表）。
10. **回滚**：渲染/渠道/服务改动独立；回退后 `PushRun` 新列保留为 `NULL`（向后兼容），旧邮件无预览。

## Open Questions

- 预览留存是否需要按天数/条数清理（控制 `email_html` 体积）？本次先不做，观察实际增长后再定。
