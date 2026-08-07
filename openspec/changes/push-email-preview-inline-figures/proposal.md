## Why

推送历史目前只记录「状态/收件人/事件数/错误/时间」，无法回看实际发出的邮件正文；管理员无法核对一封已发送邮件到底渲染成什么样、是否含图表，排查问题只能翻日志。同时，用户反馈「最近邮件正文没有图表」——排查确认：按现有规格图表是作为**邮件附件**发送的（非正文内嵌），「正文内嵌图表」在 `enhance-push-email-content` 中被列为 Non-Goal（理由是图表服务接口需鉴权、邮件外部无法访问）。但该顾虑对「CID 内嵌」并不成立：附件实现已从磁盘读到图表字节，可直接内嵌进 HTML 正文，邮件客户端无需回访任何鉴权接口即可显示。因此本次同时解决「正文看不到图表」与「历史无法预览邮件内容」两件事。

## What Changes

- **邮件正文内嵌图表**：`per_item` 事件的图表以 `Content-ID`（CID）内嵌进 HTML 正文，正文相应位置渲染 `<img src="cid:...">`，邮件客户端可直接显示图表；图表**同时保留为附件**可下载。原 Non-Goal（鉴权导致外部无法访问图表 URL）由「字节内嵌」彻底规避。
- **推送历史预览邮件内容**：每次推送执行记录一条历史时，持久化该次实际渲染并发送的邮件 HTML（含主题、附件摘要）；在「任务分析」页推送历史中，对已成功发送（至少发出 1 封邮件）的记录提供「预览」入口，弹层渲染该邮件 HTML（含内嵌图表）。
- **附件可见性**：推送历史记录中附带本次附件清单（原文件名、图表文件名、跳过原因摘要），便于核对图表是否成功附带。
- **规格更新**：`event-push` 规格的「邮件渠道渲染与发送」「推送历史记录」「邮件附件」三处 Requirement 据此修订/新增。

## Capabilities

### New Capabilities
<!-- 无新增能力，均基于已有 event-push 能力演进 -->

### Modified Capabilities
- `event-push`: 
  - 「邮件渠道渲染与发送」：新增「正文内嵌图表」要求——`per_item` 事件正文以 CID 内嵌该事件图表图片，正文不出现图表占位空缺。
  - 「推送历史记录」：新增「邮件内容留存与预览」要求——成功发送的推送须留存渲染后邮件 HTML（含主题、附件清单），并在推送历史页可预览。
  - 「邮件附件」：图表既内嵌正文又作为附件（此前仅附件）。

## Impact

- **后端模型/迁移**：`models/push.py` 的 `PushRun` 新增 `subject`/`email_html`/`attachment_summary` 列；SQLite 迁移（`core/database.py` 增量 `ALTER TABLE`）。
- **渲染层**：`services/push/render.py` 的 `PushEvent`/`render_events` 接收图表字节与 CID，HTML 正文插入 `<img src="cid:...">`；返回值携带内嵌图片清单。
- **邮件渠道**：`services/push/channels/email_channel.py` 支持内联图片 MIME 部分（`Content-Disposition: inline` + `Content-ID`），与既有附件共存于 `multipart/mixed`。
- **推送服务**：`services/push/service.py` 的 `run_push`/`_log_run` 收集每批渲染 HTML 与附件摘要并写入 `PushRun`；`_to_push_event` 携带图表。
- **附件收集**：`services/push/attachments.py` 复用既有读取逻辑，同时产出「附件」与「内嵌图片」两份字节（同源）。
- **API/Schema**：`api/analysis_tasks.py` 新增 `GET /{task_id}/push/runs/{run_id}/preview`；`schemas/push.py` 的 `PushRunOut` 增附件摘要字段。
- **前端**：`views/AnalysisTasks.vue` 推送历史卡片新增「预览」按钮 + 预览弹层（`iframe srcdoc` 渲染 HTML，含内嵌图表）；`api/push.ts` 增预览接口。
- **依赖**：无新增第三方依赖（`email.mime` 标准库即可）。
- **文档/测试**：更新需求规格说明书、设计说明书、README；新增/扩展单测覆盖内嵌图表渲染、CID 生成、预览接口、历史留存字段。
