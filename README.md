# InformationSmartAnalysisSystem
信息智能分析系统

## 分析结果页

分析任务列表的「结果」按钮打开任务结果详情页（路径 `/analysis-tasks/:id/results`），按运行批次分组，采用三段式呈现：

- `per_item` 逐条结果依次展示：① 文件信息（文件名可点击在网页预览 + 文件路径）；② 文章基本信息（标题/作者/作者单位/发布时间/页数）+ 正文内嵌图表（缩略图可查看大图）；③ 文字分析结果（markdown 渲染）。
- `aggregate` 汇总结果仅展示文字分析结果。
- 文件预览：PDF 浏览器内嵌预览、docx 下载+纯文本预览、html/md 渲染、txt 纯文本。
- 图表画廊：缩略图点击查看大图，文件与图表均经鉴权 blob 请求加载。

## 分析任务·自定义条目选择

「自定义（指定条目）」分析模式下，点击「选择条目」打开的弹窗（`AnalysisTasks.vue`）支持：

- **已选条目前排置顶**：顶部「已选条目」区始终集中展示当前已选条目，可逐条取消，不受筛选/排序影响；下方可浏览列表排除已选，避免重复。
- **列排序**：「标题/已分析/发布时间」列表头可点击排序，支持升降序切换，跨分页服务端一致。
- **标题关键词筛选**：在现有「已分析」筛选基础上新增标题模糊筛选，可组合使用。

后端 `POST /api/info-sources/items/query` 扩展可选参数 `ids`/`exclude_ids`/`sort_by`/`order`/`keyword`，排序字段经白名单（`title`/`published_at`/`analyzed`/`created_at`）校验防注入，向后兼容（不传新参数行为不变）。

## 分析任务·条目选择策略

分析任务（`per_item`/`aggregate` 模式）支持配置「条目选择策略」（`config.selection_strategy`），决定从绑定信息源中如何选取待分析条目：

- **顺序分析**（`sequential`，默认）：增量模式按入库 `id` 升序、水位线之后取最旧篇，分析后推进水位线；全量模式取全部。行为与历史版本一致。
- **最新未分析优先**（`newest_unanalyzed`）：仅从 `analyzed == False` 的条目中，按 `COALESCE(published_at, article_published_at, fetched_at)` 降序（最新在前）选取 `max_items_per_source` 篇，不依赖水位线筛选；分析后置 `analyzed = True`，下次自动跳过。时间键优先文章发布时间，回退文档元数据发布时间，再回退入库时间，覆盖 website / local_folder / freshrss 全部源类型。

前端在分析任务表单「条目选择策略」下拉中选择（自定义模式不适用，策略不生效）；也可在「高级配置 JSON」中写 `selection_strategy`（下拉值优先）。未知取值回退 `sequential`。

## 每日定时分析最新文章 + 邮件推送

借助「条目选择策略」+ 定时任务 + 推送规则，可实现每天自动分析一篇最新未分析文章并邮件推送：

1. **信息源管理**：添加信息源并同步入库。
2. **分析任务**：新建任务，绑定信息源，分析模式选「逐条分析」，条目选择策略选「最新未分析优先」，高级配置 JSON 填 `{"max_items_per_source": 1}`（每次只分析 1 篇）。
3. **定时任务**：新建定时任务，关联该分析任务，模式选「增量」，触发类型 cron，表达式如 `0 9 * * *`（每天 9 点）。
4. **推送管理**：配置 SMTP，新建推送规则，触发方式选「分析任务完成后自动」（`on_run`），勾选该分析任务与 `per_item` 事件类型，填写收件人。

每日定时触发时，引擎从未分析条目中选时间最新的 1 篇分析，完成后自动发送邮件；下一篇次日再选。

## 推送邮件内容

推送邮件正文采用卡片式三段式呈现，与系统界面一致：

- **头部**：任务名、分析类型、来源、时间（北京时间）。
- **文件信息**（`per_item`）：文件名、文件路径。
- **文章信息**（`per_item`）：作者、作者单位、发布时间、页数（空字段不显示）。
- **分析结果**：Markdown 渲染为 HTML（标题/加粗/列表/表格等），不再显示原生 Markdown 标记。

`aggregate` 事件无文件/文章信息，仅含头部与分析结果。邮件 HTML 用内联样式以兼容 QQ/163 等网页邮箱；原生 HTML 标签被转义防注入。

`per_item` 事件邮件还会附带附件：文章原文件（`local_folder` 源，PDF/docx/txt/md/html）与内嵌图表图片。附件读取复用文件服务的路径校验防穿越；单文件超 10MB 或不存在时跳过该附件并记日志，不中断推送。`aggregate` 事件无附件。

## PDF 正文抽取（视觉兜底）

`local_folder` 源的 PDF 正文抽取优先读取**文本层**（PyMuPDF `page.get_text()`）。对**扫描件/图片型 PDF**（无文本层）或**字体编码损坏的 PDF**（缺 `ToUnicode CMap`），文本层会返回空串或乱码，导致 LLM 收到"无意义编码字符串"无法分析。

为此系统新增**视觉 LLM 兜底**：当文本层质量不达标（为空、过短、或可读字符占比低于阈值）时，把 PDF 页面渲染成图片，逐页调用多模态 LLM 提取正文文本，作为 `InfoItem.content` 落库。抽取流程保持"先抽取、后分析"，分析侧无感知。

- **抽取来源**记录在 `InfoItem.extraction_method`：`text_layer`（文本层可用）/ `vision_llm`（视觉兜底成功）/ `none`（均未产出有效文本），并在分析结果接口只读返回，便于追溯。
- **优雅降级**：视觉兜底未启用、LLM 未配置、或模型不支持视觉/调用失败时，记录警告并保留原文本层内容，不中断同步或分析。
- **历史回补**：`extraction_method='none'` 或 `content` 为空的历史条目，会在同步 backfill 与手动重抽（`POST /api/info-sources/{source_id}/items/{item_id}/reextract`）时自动重新走"文本层 + 视觉兜底"。
- **部署注意**：视觉兜底需要配置一个**支持视觉的多模态 LLM**（默认 `llm.model=gpt-4o-mini` 已支持）。若分析模型不支持视觉，可单独配置 `extraction.vision_model` 指向支持视觉的模型。兜底按页消耗 LLM token，受 `max_ocr_pages` 上限约束。

## 配置

主配置文件 `config/app.json`，支持 `ISAS_*` 环境变量覆盖。本次新增配置项：

| 配置项 | 默认值 | 环境变量 | 说明 |
|---|---|---|---|
| `figures_dir` | `data/figures`（即 `data_dir/figures`） | `ISAS_FIGURES_DIR` | 内嵌图表落盘根目录，启动时自动创建 |
| `max_figures_per_item` | `20` | `ISAS_MAX_FIGURES_PER_ITEM` | 单文件图表抽取上限，超出截断并记日志 |
| `extraction.vision_fallback` | `true` | `ISAS_EXTRACTION_VISION_FALLBACK` | 是否启用 PDF 视觉 LLM 兜底抽取 |
| `extraction.vision_model` | `""`（复用 `llm.model`） | `ISAS_EXTRACTION_VISION_MODEL` | 视觉兜底专用模型，留空则复用 `llm.model` |
| `extraction.max_ocr_pages` | `10` | `ISAS_EXTRACTION_MAX_OCR_PAGES` | 单文件视觉兜底最大渲染页数，超出截断并记日志 |
| `extraction.min_text_length` | `50` | `ISAS_EXTRACTION_MIN_TEXT_LENGTH` | 文本层可读非空白字符数下限，低于则判定不可用 |
| `extraction.readable_ratio` | `0.6` | `ISAS_EXTRACTION_READABLE_RATIO` | 文本层可读字符占比阈值，低于则判定不可用 |
| `extraction.render_dpi` | `150` | `ISAS_EXTRACTION_RENDER_DPI` | 视觉兜底页面渲染 DPI（清晰度与 token 成本平衡） |

## 部署

### 存量回填

首次部署后，对现有 `local_folder` 信息源触发一次同步（同步会补齐存量元数据/图表，并对 `extraction_method='none'` 或 `content` 为空的历史条目重新走视觉兜底），或对单个文件调用 `POST /api/info-sources/{source_id}/items/{item_id}/reextract` 手动重新抽取。重抽后该条目 `analyzed` 置回 False，下次分析任务会自动重新分析。
