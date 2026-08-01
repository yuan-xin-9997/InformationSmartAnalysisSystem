## Why

推送邮件当前正文把 LLM 分析结果的 Markdown 原文用 `<pre>` 转义输出（`render.py`），用户看到的是 `#`/`**`/`-` 等原生标记，未渲染成可读样式；且邮件只含任务名/类型/来源/时间/内容，缺少系统界面上展示的文件信息（文件名、路径）与文章信息（标题/作者/作者单位/发布时间/页数），信息不完整。本次让邮件正文把 Markdown 渲染成 HTML，并补全文件信息与文章信息，使邮件内容与界面三段式呈现一致、可读且完整。

## What Changes

- 引入轻量 Markdown 渲染库 `mistune`（纯 Python，`escape=True` 转义原生 HTML），把分析结果 Markdown 渲染成 HTML 后嵌入邮件正文，替代当前 `<pre>` 原文输出。
- 扩展 `PushEvent` 数据结构，新增文件信息与文章信息字段（文件名/文件路径/标题/作者/作者单位/发布时间/页数）；`per_item` 事件填充，`aggregate` 事件留空。
- 推送服务 `_to_push_event` 从 `AnalysisResult` 关联的 `InfoItem` 取上述字段（复用既有 `InfoItem` 查询）。
- 重写 `render.py` 邮件 HTML 为卡片式三段式（头部 + 文件信息 + 文章信息 + 渲染后的分析结果），字段为空则不显示该行；纯文本备用正文同步补全文件/文章信息。
- 新增 `markdown` 依赖到 `requirements.txt`；`Jenkinsfile` 无需改动（`pip install -r requirements.txt` 自动安装）。
- 测试与文档同步更新。

## Capabilities

### New Capabilities
<!-- 无新增能力，仅修改现有 event-push 能力的邮件渲染需求。 -->

### Modified Capabilities
- `event-push`: 「邮件渠道渲染与发送」需求变更--邮件正文 MUST 把 Markdown 分析结果渲染为 HTML（不再输出原生 Markdown 标记）；`per_item` 事件邮件正文 MUST 包含文件信息（文件名/文件路径）与文章信息（标题/作者/作者单位/发布时间/页数），与系统界面三段式呈现一致；`aggregate` 事件无文件/文章信息。

## Impact

- **后端**：`src/app/backend/services/push/render.py`（重写 HTML/纯文本渲染 + Markdown 渲染）、`src/app/backend/services/push/service.py`（`_to_push_event` 取文件/文章字段）、`src/app/backend/requirements.txt`（新增 `mistune`）。
- **测试**：`src/tests/unit/test_push_render.py`（Markdown 渲染、字段缺失不显示、aggregate 无文件信息、多事件）、`test_push_service.py`（`_to_push_event` 字段填充）。
- **文档**：`README.md`、需求规格说明书、设计说明书。
- **部署**：`Jenkinsfile` 无启动/结构变化，`pip install -r requirements.txt` 自动安装新依赖。
