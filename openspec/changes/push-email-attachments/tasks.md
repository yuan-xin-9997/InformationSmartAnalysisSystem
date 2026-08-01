## 1. 附件收集模块（测试先行）

- [x] 1.1 编写测试：`collect_attachments` 对 `per_item` + `local_folder` 收集原文件 + 图表附件；`aggregate` 无附件；非 `local_folder` 源无原文件附件（图表若存在仍附）
- [x] 1.2 编写测试：路径越界跳过、文件不存在跳过、超 10MB 跳过记日志、文件名取 basename 防 header 注入
- [x] 1.3 新建 `src/app/backend/services/push/attachments.py`：`Attachment` dataclass(`filename`/`mime`/`data`) + `collect_attachments(db, results)`；原文件复用 `is_relative_to(folder_path)` 校验 + 扩展名 MIME（pdf/docx/txt/md/html）；图表复用 `is_relative_to(figures_dir)` + `fig.mime`；10MB 上限跳过记日志

## 2. 邮件渠道附件支持

- [x] 2.1 编写测试：`email_channel.send` 带 `attachments` 发 `multipart/mixed`（含附件 part）；无附件时保持 `alternative`（向后兼容）
- [x] 2.2 `src/app/backend/services/push/channels/email_channel.py` 的 `send` 加 `attachments` 参数；有附件时 `MIMEMultipart("mixed")` + 正文 `alternative` 子部分 + 附件 `MIMEBase`（`Content-Disposition: attachment`），中文文件名 RFC 2231 编码

## 3. 服务集成与文档

- [x] 3.1 `src/app/backend/services/push/service.py` 的 `run_push` 每批 `collect_attachments(db, batch)` 收集附件并传入 `channel.send`
- [x] 3.2 更新 `README.md`、需求规格说明书、设计说明书（推送邮件附件）
- [x] 3.3 运行后端全量测试通过
- [ ] 3.4 提交 Github、手工触发 Jenkins 构建；部署后手动触发一次推送，由用户确认邮件附件（原文件 + 图表）
