## 1. 数据模型与迁移

- [x] 1.1 `models/push.py` 的 `PushRun` 新增 `subject: str | None`、`email_html: Text | None`、`attachment_summary: JSON | None` 三列
- [x] 1.2 `core/database.py` 启动迁移：`ALTER TABLE push_runs ADD COLUMN` 三列（SQLite 幂等，已存在则跳过）
- [x] 1.3 单测：迁移后旧 `push_runs` 行新列为 `NULL`、新行可写入新列（`test_database.py` 或 `test_push_models.py`）

## 2. 媒体收集层（附件 + 内联图同源）

- [x] 2.1 `attachments.py` 新增 `InlineImage`（`cid/filename/mime/data/item_id`）与 `FigureRef`（`cid/mime`）dataclass；重构 `collect_attachments` 为 `collect_push_media(db, results) -> (attachments, inline_figures)`，图表字节一次读取、同时产出附件与内联图，每图分配唯一 CID
- [x] 2.2 `collect_push_media` 复用既有 `figures_dir` 路径校验、10MB 上限、跳过记日志语义；`attachment_summary` 计算（成功附件名 + 跳过原因摘要）由 service 层据返回值组装
- [x] 2.3 单测：`test_push_attachments.py` 覆盖 `per_item` 有图（内联+附件双份且 CID 唯一）、无图、路径越界跳过、超限跳过、`aggregate` 无媒体、原文件仅 `local_folder`

## 3. 渲染层（正文内嵌图表 cid:）

- [x] 3.1 `render.py` `PushEvent` 增 `figures: list[FigureRef] = []`（不存字节）
- [x] 3.2 `render_events` 在每条 `per_item` 事件分析结果后插入 `<img src="cid:{cid}" .../>`（来自 `event.figures`）；无图不插占位；`aggregate` 不插；返回值改为 `(subject, html, text, inline_images)`，`inline_images` 跨事件聚合
- [x] 3.3 单测：`test_push_render.py` 覆盖有图插入 `cid:`、无图不出现 `<img>`、`aggregate` 无图、多事件多图 CID 唯一、Markdown 渲染不回归

## 4. 邮件渠道层（related > alternative + 内联图 + 附件）

- [x] 4.1 `email_channel.py` `send` 增 `inline_images: list | None` 参数；有内联图时构造 `multipart/mixed > multipart/related > multipart/alternative(text+html) + 内联图片部分(Content-Disposition: inline, Content-ID: <cid>)`，附件仍为 `mixed` 顶层 `attachment`
- [x] 4.2 无内联图时与现状兼容（`mixed>alternative+附件` 或 `alternative`）；内联图 MIME 用 `email.mime.image.MIMEImage` 或 `MIMEBase(image/*)` + base64
- [x] 4.3 单测：`test_push_channel.py` 解析生成的 `Message`：内联部分含 `Content-ID`/`inline`、附件部分含 `attachment`、HTML 中 `cid:` 与内联部分 `Content-ID` 一一对应、无内联图时结构退化

## 5. 推送服务层（留存 + 多批合并 + 预览 HTML）

- [x] 5.1 `service.py` `_to_push_event` 接收 `item_id -> [InlineImage]`，填 `PushEvent.figures=[FigureRef(cid, mime)]`
- [x] 5.2 `run_push` 每批收集 `(subject, html, inline_images, attachments)`，传 `inline_images` 给 `channel.send`；新增 `_cid_to_data_url(html, inline_images)` 把 `cid:{cid}` 替换为 `data:{mime};base64,{data}` 生成浏览器可渲染 HTML
- [x] 5.3 多批合并：各批 `data:` HTML 按序拼接（插「第 i 封/共 N 封」分隔），`subject` 取首封，`attachment_summary` 合并；`_log_run` 接收并写入 `subject/email_html/attachment_summary`；未发送邮件（`no_new`/发送前 `failed`）这三列为 `None`
- [x] 5.4 单测：`test_push_service.py` 覆盖单批留存 `email_html` 含 `data:` 图、多批合并、`no_new` 不留存、`failed` 不推进水位线且不留存内容

## 6. API 与 Schema（预览接口 + 列表字段）

- [x] 6.1 `schemas/push.py` `PushRunOut` 增 `has_preview: bool`（派生自 `email_html is not None`）与 `attachment_summary: list | None`；新增 `PushRunPreviewOut(subject, html, attachments)`
- [x] 6.2 `api/analysis_tasks.py` 新增 `GET /{task_id}/push/runs/{run_id}/preview`（`require_page("analysis_tasks")`，校验 run 归属该任务，`email_html` 为空返回 404，否则返回 `{subject, html, attachments}`）
- [x] 6.3 `list_push_runs` 返回值携带 `has_preview`/`attachment_summary`（由 ORM 行计算）
- [x] 6.4 单测：`test_push_api.py` 覆盖预览成功、`email_html` 为空 404、run 不属于该任务 404、无 `analysis_tasks` 权限 403

## 7. 前端（预览入口 + iframe 弹层）

- [ ] 7.1 `api/push.ts` `PushRun` 类型增 `has_preview`/`attachment_summary`；新增 `getPushRunPreviewApi(taskId, runId)`
- [ ] 7.2 `AnalysisTasks.vue` 推送历史卡片：`run.has_preview` 时显示「预览」按钮；点击调接口取 `{subject, html}`
- [ ] 7.3 预览弹层：`<iframe :srcdoc="html" sandbox="allow-same-origin" referrerpolicy="no-referrer">` 渲染（含 `data:` 内嵌图）；弹层标题显示 `subject`
- [ ] 7.4 手测：成功推送后历史出现「预览」，预览含内嵌图表；`no_new` 记录无「预览」按钮

## 8. 端到端与回归

- [ ] 8.1 端到端：配置真实 SMTP，对含图表的 `per_item` 任务手动推送，验证邮件正文内嵌图表可见、图表同时为附件、推送历史可预览且预览含图
- [ ] 8.2 回归：无图表任务推送正文无破损占位；`aggregate` 推送无图无附件；`website`/`freshrss` 源无原文件附件但有图内嵌
- [ ] 8.3 全量单测通过（`pytest`），前端构建通过（`npm run build`）

## 9. 文档与部署

- [x] 9.1 更新需求规格说明书、设计说明书（推送历史预览 + 正文内嵌图表）
- [x] 9.2 更新 README（推送历史预览用法、邮件正文内嵌图表说明）
- [x] 9.3 确认 `Jenkinsfile`/`merge_app_config.py` 不覆盖部署侧 `app.json`（`figures_dir` 等保留）；提交后触发 Jenkins 手工构建并请用户验证
