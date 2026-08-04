## Why

推送邮件当前只含正文（渲染后的分析结果 + 文件/文章信息文本），收件人无法直接查看文章原文与内嵌图表。系统界面已支持文件预览与图表查看，但邮件未附带原文件与图表。本次把分析文章的原文件（PDF/docx/txt/md/html）与内嵌图表图片作为附件一并推送，使收件人无需登录系统即可查看原文与图表。

## What Changes

- 新增附件收集模块 `src/app/backend/services/push/attachments.py`：为 `per_item` 事件从关联 `InfoItem`（原文件）与 `InfoItemFigure`（图表）收集附件字节，复用文件服务的路径校验（`is_relative_to` `folder_path`/`figures_dir` 防穿越）与 MIME 判定；仅 `local_folder` 源附原文件，`website`/`freshrss` 源无原文件附件。
- `email_channel.send` 新增 `attachments` 参数，邮件结构改为 `multipart/mixed`（正文 `alternative` + 附件）。
- `service.py` 的 `run_push` 每批事件收集附件并传入 `channel.send`；`aggregate` 事件无附件。
- 单文件大小上限（默认 10MB），超限跳过并记日志，避免邮件超 SMTP 体积限制。
- 测试与文档同步。

## Capabilities

### New Capabilities
<!-- 无新增能力，仅在现有 event-push 能力新增「邮件附件」需求。 -->

### Modified Capabilities
- `event-push`: 新增「邮件附件」需求--`per_item` 事件推送邮件 MUST 把文章原文件（`local_folder` 源）与内嵌图表图片作为附件一并发送；附件读取 MUST 复用文件服务的路径校验防穿越；单文件超大小上限时跳过该附件并记日志，不中断推送。

## Impact

- **后端**：`src/app/backend/services/push/attachments.py`（新增）、`src/app/backend/services/push/channels/email_channel.py`（附件支持）、`src/app/backend/services/push/service.py`（集成附件收集）。
- **测试**：`src/tests/unit/test_push_attachments.py`（新增，附件收集与路径校验/大小上限）、`test_push_channels.py`（带附件发送）。
- **文档**：`README.md`、需求规格说明书、设计说明书。
- **部署**：无新依赖、无启动变化，`Jenkinsfile` 不动。
