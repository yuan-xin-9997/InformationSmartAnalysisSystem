## Context

推送邮件渲染当前实现（`services/push/render.py`）：

- `PushEvent` 仅含 `task_name`/`result_type`/`source_name`/`content`/`created_at`（`render.py:17-25`）。
- HTML 把每条事件渲染成表格一行，内容列用 `<pre>{escape(e.content)}</pre>`（`render.py:46`），即把 LLM 分析结果的 Markdown 原文转义后塞进 `<pre>`，导致邮件里出现 `#`/`**`/`-` 等原生标记，未渲染。
- 纯文本备用正文用 `content` 原文（`render.py:65`）。
- `_to_push_event`（`services/push/service.py:41-50`）只解析 task/source 名称，未取 `InfoItem` 的文件/文章元数据。

而分析结果接口 `_result_out`（`api/analysis_tasks.py:226-269`）已组装 `SourceFileOut`（`filename`/`file_path`/`title`/`author`/`author_affiliation`/`published_at`/`page_count`/`file_url`/`figures`），前端 `TaskResults.vue` 据此三段式呈现（文件信息 + 文章信息 + Markdown 渲染结果）。推送邮件未复用这些信息。

后端依赖（`requirements.txt`）无 Markdown 渲染库；前端用 `marked` + `dompurify`（`utils/markdown`）。约束：CLAUDE.md 不硬编码环境信息、时间显示北京时间、优先 SQLite/Python、无明文禁止新依赖（推送发送模块此前用 stdlib，但 Markdown 渲染需引入库）。

## Goals / Non-Goals

**Goals:**
- 邮件 HTML 正文把分析结果 Markdown 渲染为 HTML，不再出现原生 Markdown 标记。
- `per_item` 事件邮件正文包含文件信息（文件名/文件路径）与文章信息（标题/作者/作者单位/发布时间/页数），与界面三段式一致；字段为空不显示。
- 纯文本备用正文同步补全文件/文章信息。
- `aggregate` 事件仅含任务/类型/来源/时间 + 分析结果。

**Non-Goals:**
- 不在邮件中内嵌图表图片（图表服务接口需鉴权，邮件外部无法访问）。
- 不放文件预览链接（同鉴权限制；邮件仅展示文件名与路径文本）。
- 不改推送规则、触发方式、增量水位线、SMTP 配置逻辑。
- 不改前端；不改 `AnalysisResult` API。

## Decisions

### 决策 1：引入 `mistune` 库渲染 Markdown
新增 `mistune`（PyPI，纯 Python）到 `requirements.txt`，用 `mistune.create_markdown(escape=True, plugins=["table", "strikethrough", "fenced_code"])` 把分析结果渲染为 HTML。
**理由**：轻量纯 Python；`escape=True` 默认转义原生 HTML 标签（防邮件 HTML 注入，与既有渲染测试 `<script>` 被转义的语义一致）；plugins 支持表格/删除线/代码块（LLM 常输出表格）；与前端 `marked` 渲染风格接近。
**备选**：`markdown`（PyPI）--未选（默认保留 raw HTML，需额外 `bleach` 过滤才安全，增依赖）；自实现转换--否（易出错、难覆盖 GFM）。

### 决策 2：Markdown 渲染安全性
`mistune` 以 `escape=True` 运行，原生 HTML 标签（如 `<script>`）被转义为实体，仅 Markdown 语法被渲染为 HTML 标签。无需额外引入 `bleach`。
**理由**：邮件网页客户端可能渲染 HTML，需防注入；`escape=True` 在渲染层即解决，零额外依赖。
**备选**：`markdown` + `bleach` 白名单--否（多一个依赖、配置复杂）。

### 决策 3：`PushEvent` 扩展文件/文章字段
`PushEvent` 新增 `item_title`/`file_path`/`author`/`author_affiliation`/`article_published_at`/`page_count`（均可空）；`per_item` 填充，`aggregate` 全空。
**理由**：与 `SourceFileOut` 字段对齐，复用界面已有信息；可空设计让 `aggregate` 自然不显示。
**备选**：直接传 `SourceFileOut` 对象--否（推送渲染应与 ORM/解耦，`PushEvent` 是扁平 dataclass，保持现有解耦风格）。

### 决策 4：`_to_push_event` 查 `InfoItem` 取字段
`_to_push_event` 在现有 task/source 查询基础上，按 `r.info_item_id` 查 `InfoItem`，填充新增字段。
**理由**：复用既有 `AnalysisResult.info_item_id` 关联；`per_item` 必有 `info_item_id`，`aggregate` 为 None 不查。
**备选**：批量预取 `InfoItem`（如 `_result_out` 的 `items_map`）--否（单次推送批量已由 `_collect_events` 取出结果，可在 `_to_push_event` 内按需查；批次规模由 `max_events_per_email` 限制，N+1 可接受。如后续性能需要再优化为批量预取）。

### 决策 5：HTML 卡片式三段式 + 内联样式
每条事件渲染为一个卡片区块（非大表格）：头部（任务/类型/来源/时间）-> 文件信息（文件名/路径）-> 文章信息（标题/作者/作者单位/发布时间/页数）-> 分析结果（渲染后 HTML）。字段为空不显示该行。样式用内联 `style` + 表格布局以保证邮件客户端兼容。
**理由**：与界面三段式心智一致；内联样式兼容 QQ/163 等网页邮箱（其常剥离 `<style>`）。
**备选**：保留单表格布局--否（信息增多后表格过宽难读）；`<style>` 块--否（邮件客户端兼容性差）。

### 决策 6：纯文本正文同步补全
纯文本正文在每条事件下补充文件/文章信息行（`文件: ...`、`作者: ...` 等），分析结果保留 Markdown 原文（纯文本无需渲染）。
**理由**：纯文本客户端也能看到完整信息；纯文本里 Markdown 原文可读。

## Risks / Trade-offs

- **新增 `markdown` 依赖** -> `requirements.txt` 增一行，Jenkinsfile `pip install` 自动安装；`.venv` 本地需 `pip install markdown` 跑测试。
- **LLM 输出含异常 Markdown 导致渲染怪异** -> `markdown` 库容错性好；最坏退化为可读文本，不报错。
- **邮件客户端 CSS 兼容** -> 用内联样式 + 表格布局，QQ/163/Outlook 等主流客户端兼容；不依赖 `<style>`。
- **`_to_push_event` 按条查 `InfoItem`** -> 批次受 `max_events_per_email`（默认 50）限制，可接受；后续若性能需可优化为批量预取。
- **字段缺失** -> 文件/文章信息字段为空时不显示该行，避免空值占位。

## Migration Plan

1. **依赖**：`requirements.txt` 新增 `markdown>=3.5`；本地 `.venv` 安装。
2. **render.py**：引入 `markdown`；`PushEvent` 加字段；重写 `render_events` 为卡片式三段式 HTML + 同步纯文本；Markdown 渲染。
3. **service.py**：`_to_push_event` 查 `InfoItem` 填充新字段。
4. **测试**：`test_push_render.py` 覆盖 Markdown 渲染、字段缺失不显示、aggregate 无文件信息、多事件；`test_push_service.py` 覆盖 `_to_push_event` 字段填充。
5. **文档**：README、需求规格说明书、设计说明书。
6. **回滚**：render/service 改动独立；移除 `markdown` 依赖即回退（`<pre>` 原文）。

## Open Questions

- 是否需要邮件内嵌图表缩略图？需公开可访问的图表 URL（带 token 或公网图床），本次 Non-Goal，后续可评估。
