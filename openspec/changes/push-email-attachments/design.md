## Context

推送邮件当前（`services/push/channels/email_channel.py`）用 `MIMEMultipart("alternative")` 只发 HTML + 纯文本正文，无附件。文件服务（`api/info_sources.py` `get_item_file` / `get_item_figure`）已有原文件与图表字节读取逻辑：

- 原文件：仅 `local_folder` 源，`Path(item.external_id)`，校验 `resolved.is_relative_to(Path(src.config["folder_path"]).resolve())`，MIME 按扩展名（pdf/docx/txt/md/html）。
- 图表：`Path(fig.storage_path)`，校验 `is_relative_to(settings.figures_dir.resolve())`，MIME = `fig.mime`。

本次复用这套读取 + 路径校验逻辑，把原文件与图表作为邮件附件发送。约束：不硬编码路径（复用 `folder_path`/`figures_dir`）；优先 SQLite/Python；无新依赖（`email.mime` 标准库）。

## Goals / Non-Goals

**Goals:**
- `per_item` 事件推送邮件附原文件（`local_folder`）+ 内嵌图表图片附件。
- 复用文件服务路径校验防穿越；文件不存在/越界跳过。
- 单文件大小上限，超限跳过记日志，不中断推送。
- `email_channel` 支持附件，向后兼容（无附件时行为不变）。

**Non-Goals:**
- 不对 `website`/`freshrss` 源生成原文件附件（无本地文件）。
- 不做附件压缩/打包；不做附件总大小硬限制（批次规模小，单文件上限即可）。
- 不改文件服务接口；不改正文渲染。

## Decisions

### 决策 1：新建 `attachments.py` 模块收集附件
新增 `services/push/attachments.py`，`collect_attachments(db, results) -> list[Attachment]`，`Attachment` 为 dataclass(`filename`, `mime`, `data: bytes`)。遍历 `results` 的 `per_item` 结果（跳过 `aggregate`），按 `info_item_id` 取 `InfoItem` + `InfoItemFigure`，收集原文件 + 图表。
**理由**：附件收集逻辑独立于渲染与发送，便于测试与复用。
**备选**：在 `service.py` 内联收集--否（逻辑较多，独立模块更清晰）。

### 决策 2：原文件附件仅 `local_folder`，复用路径校验
原文件：`source.type == "local_folder"` 时，`Path(item.external_id).resolve()` 校验 `is_relative_to(Path(src.config["folder_path"]).resolve())`，读字节，MIME 按扩展名（`.pdf`->`application/pdf`、`.docx`->docx 媒体类型、`.txt`/`.md`/`.html`/`.htm`->`text/plain`），`filename = item.title or Path.name`。其他源类型跳过原文件。
**理由**：与 `get_item_file` 完全一致的校验，防穿越；`website`/`freshrss` 无本地文件。
**备选**：对 `website` 抓取的 HTML 生成 `.html` 附件--否（无本地文件，超范围）。

### 决策 3：图表附件复用 `figures_dir` 校验
图表：`Path(fig.storage_path).resolve()` 校验 `is_relative_to(settings.figures_dir.resolve())`，读字节，MIME = `fig.mime`，`filename = f"{item.title or 'figure'}_{fig.figure_index}{suffix}"`（suffix 从 `storage_path` 取）。
**理由**：与 `get_item_figure` 一致；图表对所有源类型均可能存在（实际 `local_folder` 才抽取图表）。

### 决策 4：单文件大小上限 10MB，超限/不存在/越界跳过并记日志
`_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024`。文件 `stat().st_size` 超限、`exists()` 为假、`is_relative_to` 失败均跳过，`_logger.warning` 记日志，继续其余附件。
**理由**：避免邮件超 SMTP 体积限制（常见 25MB）；跳过而非失败，保证推送可用。
**备选**：失败整封邮件--否（附件缺失不应阻断推送）。

### 决策 5：`email_channel.send` 加 `attachments` 参数，`multipart/mixed`
`send(cfg, recipients, subject, html, text, attachments=None)`。无附件时保持 `MIMEMultipart("alternative")`（向后兼容）；有附件时用 `MIMEMultipart("mixed")`，正文 `alternative` 作为第一个子部分，每个附件用 `email.mime.base.MIMEBase(maintype, subtype)` + `set_payload` + `Content-Disposition: attachment; filename=...`。文件名用 `email.utils` 处理中文（RFC 2231 `filename*`）。
**理由**：标准库 `email.mime` 即可，无新依赖；`mixed` 是附件邮件标准结构。
**备选**：始终 `mixed`--否（无附件时 `alternative` 更简洁，向后兼容现有测试）。

### 决策 6：文件名安全处理
附件 `filename` 去除路径分隔符（取 `Path(name).name`），防 `Content-Disposition` header 注入；中文用 RFC 2231 编码（`email.header` 处理）。
**理由**：防 header 注入；兼容邮件客户端中文文件名。

### 决策 7：`service.py` 每批收集附件传入发送
`run_push` 在每批 `results` 渲染后，`collect_attachments(db, batch)` 收集附件，`channel.send(cfg, recipients, subject, html, text, attachments=attachments)`。失败不推进水位线（沿用现有语义）。
**理由**：附件随批次发送；发送失败重试时附件一并重发。

## Risks / Trade-offs

- **大附件导致 SMTP 慢/超时** -> 单文件 10MB 上限；`_SMTP_TIMEOUT` 适当增大（或保持 30s，附件通常小）。
- **文件被删/移动** -> `exists()` 检查，跳过记日志。
- **路径穿越** -> `is_relative_to` 校验（与文件服务一致）。
- **文件名特殊字符/中文** -> `Path.name` 取 basename + RFC 2231 编码。
- **一批多事件附件多** -> 受 `max_events_per_email` 限制；用户场景每天1篇，附件少。
- **向后兼容** -> `attachments=None` 时 `alternative` 结构不变，既有测试不受影响。

## Migration Plan

1. **attachments.py**：新建 `Attachment` + `collect_attachments`，复用路径校验读字节。
2. **email_channel.py**：`send` 加 `attachments` 参数，`mixed` 结构 + 附件。
3. **service.py**：`run_push` 每批 `collect_attachments` + 传入 `send`。
4. **测试**：`test_push_attachments.py`（收集、路径校验、大小上限、aggregate 无附件、非 local_folder 无原文件）；`test_push_channels.py`（带附件发送）。
5. **文档**：README、需求规格说明书、设计说明书。
6. **回滚**：`attachments` 参数可选，`attachments.py` 独立，移除即回退。

## Open Questions

- 是否需要附件总大小上限（除单文件外）？暂不做，批次规模小；后续若问题再加。
