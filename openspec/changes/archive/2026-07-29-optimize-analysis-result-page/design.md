## Context

分析结果页 `src/app/frontend/src/views/TaskResults.vue`（由「分析任务」页 `AnalysisTasks.vue` 的「结果」按钮经路由 `task-results` 打开）目前是极简文字手风琴：按 `TaskRun` 批次列出 `AnalysisResult`，每条仅展示 `result_type`、`source_name`、`created_at` 与 LLM `content`。

后端现状（经代码勘探确认）：
- `AnalysisResult`（`models/analysis.py`）只有 `id/task_run_id/task_id/source_id/info_item_id/result_type/content/created_at`；`AnalysisResultOut`（`schemas/analysis.py`）不携带来源文件名/路径/标题，只有 `info_item_id` 外键。
- `InfoItem`（`models/info_source.py`）对 `local_folder` 源把文件名存为 `title`、绝对路径存为 `external_id`/`url`、纯文本存为 `content`、文件 mtime 存为 `published_at`；**无** `author`/`author_affiliation`/`page_count`，**无**图表字段。
- 抽取逻辑 `services/info_source/local_folder.py` 的 `extract_text` 仅取纯文本：PDF 用 PyMuPDF `page.get_text()`、docx 用 python-docx 段落、HTML 用 BeautifulSoup、txt/md 原文；**不读** `doc.metadata`/`page_count`，**不提取**图片。
- 无文件预览/服务接口（`main.py` 仅 StaticFiles 服务 SPA）；无文件上传接口；文件只通过 `local_folder` 源从磁盘路径进入。
- 依赖：PyMuPDF==1.25.2、python-docx==1.1.2、beautifulsoup4、lxml；无 Pillow、无 docx→html 转换器。

约束：用户决策--作者单位优先正文启发式抽取、抽取不到留空；文件预览分级且不引入新依赖；图表仅提取内嵌图片。CLAUDE.md 要求：下载文件按年/月/日存 `data`、不硬编码环境信息、时间显示北京时间、`data` 目录不入 `.gitignore`。

## Goals / Non-Goals

**Goals:**
- 结果页 `per_item` 结果改为三段式：文件信息（可点击预览）→ 文章基本信息（标题/作者/作者单位/发布时间/页数）+ 正文内嵌图表 → 文字分析结果。
- 后端抽取并存储 `local_folder` 文件的文章元数据与内嵌图表，结果 API 一次返回全部三段数据。
- 提供按 `InfoItem` 校验的文件预览与图表服务接口，防路径穿越。
- 存量 `InfoItem` 可经下次同步或手动重新抽取回填。
- 不引入新依赖。

**Non-Goals:**
- 不做文件上传（文件仍经 `local_folder` 源从磁盘进入）。
- 不做矢量图表/绘图检测、不做 OCR、不做图表标题语义识别。
- 不为 web/RSS 源新增文件预览/页数/图表（其无本地文件）；其已有 `title`/`published_at` 可在元数据区按已有值展示，但不强制抽取。
- 不引入 docx→HTML 转换依赖（docx 仅下载 + 纯文本预览）。
- 不改动分析引擎 `services/analysis/engine.py` 的 LLM 调用与 `aggregate` 语义。

## Decisions

### 决策 1：元数据/图表的存储模型--扩展 `InfoItem` 列 + 新增 `InfoItemFigure` 表
`InfoItem` 增加可空列 `author`、`author_affiliation`、`article_published_at`、`page_count`；新增 `InfoItemFigure`（`id`、`item_id` 外键级联删除、`figure_index`、`storage_path`、`mime`、`width`、`height`、`caption`、`created_at`）。
**理由**：列式存储可在结果 API 中直接 join 返回，便于查询与回填；图表多值用独立表。
**备选**：把元数据/图表塞进 `InfoItem.content` 旁的 JSON 字段--被否，不可查询、join 困难。

### 决策 2：抽取时机--在 `local_folder` 同步时抽取并持久化（非懒加载）
在 `LocalFolderAdapter.fetch_new_items()` 抽取文本的同时抽取元数据与图表并写入 DB；图表按 `data/figures/YYYY/MM/DD/` 落盘。
**理由**：结果页单次取数即可渲染；保证一致；`reextract` 可幂等重算。
**备选**：结果页打开时懒抽取--被否，首次打开慢、重复抽取、并发落盘复杂。

### 决策 3：作者单位--首页正文启发式，抽不到留空
取首页（PDF 第 1 页 / docx 前 N 段 / HTML `<header>` 或前若干段）文本，按机构关键词正则（`大学|学院|研究所|研究院|公司|实验室|医院|Department|University|Institute|Lab|College` 等）匹配行，命中则取该行（去除多余空白）作为 `author_affiliation`；无命中留空。
**理由**：PDF/Word 标准属性无作者单位字段；按用户决策优先正文启发式、抽不到留空。
**备选**：仅留空--被否（用户明确要求优先尝试抽取）；调用 LLM 抽取--被否（增加成本与延迟，本次保持规则化）。

### 决策 4：图表存储--原始字节落盘，不引入 Pillow
PDF 用 `page.get_images()` + `doc.extract_image(xref)` 取字节与扩展名；docx 遍历 `document.part.rels` 中 `image/*` 关系取字节。按 `data/figures/YYYY/MM/DD/{item_id}_{index}.{ext}` 落盘，`InfoItemFigure` 记 `storage_path`/`mime`；宽高从图像头解析（无 Pillow 时对 PNG/JPEG 读头字节，解析失败留空）。
**理由**：用户决策不引入新依赖；PyMuPDF/python-docx 已能取字节。
**备选**：引入 Pillow 统一转码/缩略--被否（违背无新依赖决策）；图表存 DB BLOB--被否（SQLite 膨胀、不利于按年月日归档）。

### 决策 5：文件预览分级，无新依赖
`GET /api/info-sources/{source_id}/items/{item_id}/file`：按 `InfoItem` 归属解析磁盘路径后，依扩展名返回--PDF `Content-Disposition: inline` + `application/pdf`（浏览器原生预览）；HTML/txt/md 以 `text/html` 或 `text/plain` 返回供前端渲染；docx 返回 `attachment` 下载，前端另请求该 `InfoItem` 的 `content` 展示纯文本预览。
**理由**：用户决策分级预览、无新依赖。
**备选**：引入 mammoth 做 docx→HTML--被否（新依赖）；统一只下载--被否（用户要求网页预览）。

### 决策 6：安全--按 `InfoItem` 归属解析路径，双重校验防穿越
接口仅接受 `source_id`+`item_id`，由 DB 查 `InfoItem.external_id`/`url` 得到磁盘路径，**不接受**任何路径查询参数；额外校验解析出的路径必须位于该源 `config.folder_path` 之下（`Path.resolve()` 前缀比对），跨源或越界返回 403/404；磁盘缺失返回 404。
**理由**：杜绝路径穿越与跨源访问。
**备选**：仅信任 DB 值--被否（`external_id` 历史可能被污染，需纵深防御）。

### 决策 7：结果 API 扩展--`AnalysisResultOut` 内嵌 `source_file` 对象
`AnalysisResultOut` 增加可空嵌套对象 `source_file`：`{filename, file_path, title, author, author_affiliation, published_at, page_count, figures: [{index, url, mime, width, height}]}`。后端在 `api/analysis_tasks.py` 的 results 查询里一次性 join `InfoItem` 及其 `InfoItemFigure`（按 `info_item_id` 批量预取，避免 N+1）；`aggregate` 结果该对象为 `null`。
**理由**：结果页单次取数渲染三段（满足规格）；批量预取避免 N+1。
**备选**：新增 `GET /results/{result_id}/detail` 逐条拉取--被否（N+1、交互卡顿）。

### 决策 8：存量回填--下次同步幂等补齐 + 手动 reextract
同步逻辑改为：即使 `content_hash` 未变（文件已存在），若 `InfoItem` 缺元数据或图表记录，则补抽；`POST /api/info-sources/{source_id}/items/{item_id}/reextract` 对单文件即时重抽并 upsert（先清旧图表记录再重落盘）。
**理由**：最小运营成本；幂等可重复。
**备选**：仅新文件生效--被否（存量无法补，违背用户期望）。

### 决策 9：SQLite 列迁移
项目用 `Base.metadata.create_all` 建表，对已存在的 `InfoItem` 表新增列需 `ALTER TABLE ADD COLUMN`（SQLite 支持）。在 `core/db.py`（或现有初始化处）启动时检测并补列；新表 `InfoItemFigure` 由 `create_all` 自动建出。
**理由**：无 Alembic，沿用轻量迁移。
**备选**：引入 Alembic--被否（项目未采用，过度工程）。

## Risks / Trade-offs

- **作者单位启发式误抽/漏抽** -> 命中阈值保守、抽不到留空；可手动 `reextract`；UI 标注「自动抽取」。
- **扫描版 PDF（图片型）整页被当图表提取** -> 受单文件图表上限截断并记日志；宽高解析失败留空不影响展示。
- **docx 预览体验弱（仅文本）** -> 本次接受；未来可加 mammoth 升级。
- **大文件/多图表占磁盘** -> 按年/月/日归档 + 单文件图表上限 + 可配置；不存入 SQLite。
- **存量 `InfoItem.external_id` 绝对路径在迁移/换机后失效** -> 预览返回明确 404，提示重新同步。
- **路径穿越** -> 双重校验（DB 归属 + `folder_path` 前缀比对）。
- **结果 API join 增大开销** -> 批量预取 `InfoItem`/`InfoItemFigure`，避免 N+1；`limit` 已有上限（≤500）。

## Migration Plan

1. 后端模型：`InfoItem` 加列、新增 `InfoItemFigure`；启动时 `ALTER TABLE` 补列、`create_all` 建新表。
2. 后端抽取：`local_folder.py` 增元数据 + 图表抽取与落盘；同步逻辑补齐存量。
3. 后端 Schema/API：扩展 `AnalysisResultOut` 与 results 查询；新增 file/figure/reextract 接口。
4. 前端：重建 `TaskResults.vue` 的 `per_item` 卡片为三段式；新增预览弹层与图表画廊；扩展 TS 类型与 `api` 模块。
5. 测试：抽取（含作者单位启发式与留空）、图表落盘、预览接口路径穿越防护、results 关联字段、前端 `npm run build`。
6. 部署：首次部署后对现有 `local_folder` 源触发一次同步或手动 `reextract` 补齐存量。
7. 回滚：后端新列可空、新表与新接口独立；前端改动隔离在 `TaskResults.vue` 与新组件，回滚不影响现有文字结果查看。

## Open Questions

- 单文件图表数量上限默认值：建议 20（`config/app.json` 可配）。
- 是否在结果页对 web/RSS 源也展示已有 `title`/`published_at`：建议「有则展示」，但不为其新增文件预览/页数/图表（本次 Non-Goal）。
