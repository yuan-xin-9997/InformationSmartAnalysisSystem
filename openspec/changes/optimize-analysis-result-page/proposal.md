## Why

分析结果页（`TaskResults.vue`，由「分析任务」页的「结果」按钮打开）目前只是一个极简的文字手风琴：按运行批次列出 `AnalysisResult`，每条仅展示 `result_type`、`source_name`、`created_at` 和 LLM 生成的 `content`。用户看不到本次分析到底分析了哪个文件、文件在哪、也无法预览源文件；更看不到文章标题、作者、作者单位、发布时间、页数等基本信息，正文里的图表也被丢弃。这导致分析结果缺少溯源与上下文，难以核验。优化后，结果页将先展示「文件信息（可点击预览）→ 文章基本信息与图表 → 最后才是文字分析结果」，让分析产出可溯源、可核对。

## What Changes

- **结果页结构重组**：每条 `per_item` 分析结果改为三段式呈现——① 文件信息（文件名 + 文件路径，文件名可点击在网页预览文件内容）；② 文章基本信息（文章标题、作者、作者单位、文章发布时间、文件页数）+ 正文内嵌图表；③ 文字分析结果（现有 LLM `content`）。`aggregate` 汇总结果无单一文件，保持仅展示文字结果。
- **后端元数据抽取与存储**：`local_folder` 源同步时，除现有纯文本外，额外抽取并存储文章元数据（标题、作者、作者单位、发布时间、页数）与正文内嵌图片。标题/作者/发布时间/页数取自 PDF/Word 文档属性；**作者单位优先从首页正文启发式抽取（匹配「大学/学院/研究所/公司/实验室/Department/University/Institute」等关键词的行），抽取不到则留空**。
- **后端图表抽取与存储**：提取 PDF（PyMuPDF `get_images`/`extract_image`）与 Word（python-docx 内嵌图片部件）中的内嵌位图，按「年/月/日」存放于 `data` 目录下，并记录归属 `InfoItem`。
- **后端结果 API 扩展**：`AnalysisResultOut` 增加来源文件信息（文件名、文件路径、标题）及元数据、图表列表（通过关联 `InfoItem` 一次性返回），使结果页单次取数即可渲染三段内容。
- **后端文件预览与图表接口**：新增按 `InfoItem` 校验的源文件预览接口（PDF 内联预览、HTML/txt/md 直接渲染、docx 提供下载 + 已抽取纯文本预览；**禁止路径穿越，仅按 InfoItem 归属校验后服务文件**）与图表图片服务接口。
- **存量数据回填**：已有 `InfoItem` 在下次同步时重新抽取元数据与图表；并提供「手动重新抽取」入口，按需补齐存量。
- **不引入新依赖**：复用现有 PyMuPDF、python-docx、beautifulsoup4、lxml；图表以原始字节存储/服务，不引入 Pillow 等。

## Capabilities

### New Capabilities
- `analysis-result-presentation`: 优化分析结果页的端到端呈现——来源文件元数据与图表的抽取存储、结果 API 扩展、文件预览与图表服务、以及结果页「文件信息（可预览）→ 文章基本信息与图表 → 文字分析结果」的三段式展示。

### Modified Capabilities
<!-- 现有 specs 仅有 event-push，与本变更无关；本变更为新增能力，无被修改的现有能力。 -->

## Impact

- **后端模型**（`models/info_source.py`）：`InfoItem` 增列 `author`、`author_affiliation`、`article_published_at`、`page_count`；新增 `InfoItemFigure`（`item_id`、`figure_index`、`storage_path`、`mime`、`width`/`height`、`caption`），复用现有建表/迁移机制。
- **后端抽取**（`services/info_source/local_folder.py`）：在 `extract_text` 旁新增元数据抽取（PyMuPDF `doc.metadata`/`doc.page_count`、python-docx `core_properties`、HTML `<meta>`/`<title>`）与作者单位首页启发式抽取；新增内嵌图片抽取并按年/月/日落盘 `data`。
- **后端 Schema**（`schemas/analysis.py`、`schemas/info_source.py`）：`AnalysisResultOut` 增加来源文件/元数据/图表嵌套字段；新增文件预览与图表响应 schema。
- **后端 API**（`api/analysis_tasks.py`、`api/info_sources.py`）：结果接口关联 `InfoItem` 返回三段数据；新增 `GET /api/info-sources/{source_id}/items/{item_id}/file`（预览/下载，按 InfoItem 校验防路径穿越）、`GET /api/info-sources/{source_id}/items/{item_id}/figures/{index}`、`POST .../items/{item_id}/reextract`（手动重新抽取）。
- **前端**（`views/TaskResults.vue`、`api/tasks.ts`/`api/sources.ts`）：重建 `per_item` 结果卡片为三段式；新增文件预览弹层（PDF 用 `iframe` 内嵌、HTML/txt/md 直接渲染、docx 下载 + 纯文本预览）与图表画廊；沿用现有自定义 CSS 设计体系（无 UI 库）。
- **配置**（`core/config.py`、`config/app.json`）：图表存储目录（`data` 下，按年/月/日）、单文件图表数量上限等可配置项。
- **测试**：元数据抽取（含作者单位启发式与留空）、图表抽取与落盘、预览接口路径穿越防护、结果 API 关联字段、前端 `npm run build` 冒烟。
- **文档**：更新 README、需求规格说明书、设计说明书；Jenkinsfile 无依赖/启动变化则不动。
