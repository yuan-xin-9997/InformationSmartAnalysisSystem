## 1. 依赖与渲染重写（测试先行）

- [x] 1.1 `src/app/backend/requirements.txt` 新增 `mistune>=3.0`；本地 `.venv` 安装 `mistune`
- [x] 1.2 编写测试：`render_events` 把分析结果 Markdown 渲染为 HTML（标题/加粗/列表/表格），HTML 中不出现原生 Markdown 标记（如 `**`、`# `）
- [x] 1.3 编写测试：`per_item` 事件 HTML 含文件名/文件路径/标题/作者/作者单位/发布时间/页数；某字段为空时不显示该行
- [x] 1.4 编写测试：`aggregate` 事件 HTML 不含文件/文章信息；纯文本备用正文含文件/文章信息行，分析结果保留 Markdown 原文
- [x] 1.5 编写测试：多事件（批次）渲染，每事件独立卡片
- [x] 1.6 重写 `src/app/backend/services/push/render.py`：`PushEvent` 新增 `item_title`/`file_path`/`author`/`author_affiliation`/`article_published_at`/`page_count` 可空字段；`render_events` 渲染卡片式三段式 HTML（头部+文件信息+文章信息+Markdown 渲染的分析结果，字段空不显示行，内联样式）与同步纯文本；用 `mistune`（`escape=True`，plugins=["table","strikethrough","task_lists","url"]）渲染

## 2. 推送服务取数

- [x] 2.1 编写测试：`_to_push_event` 对 `per_item` 结果从关联 `InfoItem` 填充文件/文章字段；`aggregate`（`info_item_id=None`）字段留空
- [x] 2.2 `src/app/backend/services/push/service.py` 的 `_to_push_event` 按 `r.info_item_id` 查 `InfoItem`，填充新增字段

## 3. 文档与验证

- [x] 3.1 更新 `README.md`、需求规格说明书、设计说明书（推送邮件内容：Markdown 渲染 + 文件/文章信息）
- [x] 3.2 运行后端全量测试通过
- [ ] 3.3 提交 Github、手工触发 Jenkins 构建；部署后手动触发一次推送，由用户确认邮件效果（Markdown 已渲染、信息完整）
