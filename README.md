# InformationSmartAnalysisSystem
信息智能分析系统

## 任务分析（三页合一）

原「分析任务」「定时任务」「推送管理」三个页面已合并为单一的「任务分析」页（`/analysis-tasks`），以分析任务为中心一体化配置：

- **任务列表**：每个任务卡片展示「定时」「推送」状态摘要（如 `定时：每天9点`、`推送：2 收件人·完成后自动`，未配置则显示「未配置」），归属一目了然。
- **编辑弹窗三分区（Tab）**：
  - **基本信息**：名称、说明、分析模式、条目选择策略、绑定信息源、自定义条目选择、高级配置 JSON。
  - **定时分析**：启用开关、执行模式（全量/增量）、触发类型（cron/间隔）、cron 表达式或间隔秒数。每任务至多一条定时配置。
  - **推送配置**：启用开关、事件类型、收件人、触发方式（完成后自动/定时/仅手动）、定时参数、每封邮件最大事件数。每任务至多一条推送配置。
  - 保存时三区一次性提交；不启用的子配置以 `null` 下发表示删除。
- **全局邮件通道（SMTP）**：页面底部折叠区，承载 SMTP 配置/保存/测试（页面配置优先于 `config/app.json` 的 `email` 段）。
- **按任务推送历史**：任务卡片「推送历史」按钮查看该任务推送配置的历次推送记录。
- 旧路由 `/scheduled-jobs`、`/push-management` 重定向到 `/analysis-tasks`；页面权限键收敛为 `analysis_tasks`（原 `scheduled_jobs`、`push_management` 已移除，存量用户权限在迁移时自动授予 `analysis_tasks`）。

> 数据模型变更：推送规则由多任务（`task_ids` 数组）改为单任务 1:1（`task_id`）；定时任务收敛为每任务 1:1。详见下文「部署·三页合一迁移」。

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

前端在任务分析编辑弹窗「条目选择策略」下拉中选择（自定义模式不适用，策略不生效）；也可在「高级配置 JSON」中写 `selection_strategy`（下拉值优先）。未知取值回退 `sequential`。

## 每日定时分析最新文章 + 邮件推送

借助「条目选择策略」+ 任务分析页的「定时分析」与「推送配置」，可实现每天自动分析一篇最新未分析文章并邮件推送：

1. **信息源管理**：添加信息源并同步入库。
2. **任务分析**：新建分析任务，绑定信息源，分析模式选「逐条分析」，条目选择策略选「最新未分析优先」，高级配置 JSON 填 `{"max_items_per_source": 1}`（每次只分析 1 篇）。
3. **定时分析**：在同一任务编辑弹窗的「定时分析」Tab 启用定时，模式选「增量」，触发类型 cron，表达式如 `0 9 * * *`（每天 9 点）。
4. **推送配置**：在「推送配置」Tab 启用推送，触发方式选「分析任务完成后自动」（`on_run`），勾选 `per_item` 事件类型，填写收件人；并在页面底部「邮件通道（SMTP）」配置 SMTP。

每日定时触发时，引擎从未分析条目中选时间最新的 1 篇分析，完成后自动发送邮件；下一篇次日再选。

## 推送邮件内容

推送邮件正文采用卡片式三段式呈现，与系统界面一致：

- **头部**：任务名、分析类型、来源、时间（北京时间）。
- **文件信息**（`per_item`）：文件名、文件路径。
- **文章信息**（`per_item`）：作者、作者单位、发布时间、页数（空字段不显示）。
- **分析结果**：Markdown 渲染为 HTML（标题/加粗/列表/表格等），不再显示原生 Markdown 标记。

`aggregate` 事件无文件/文章信息，仅含头部与分析结果。邮件 HTML 用内联样式以兼容 QQ/163 等网页邮箱；原生 HTML 标签被转义防注入。

`per_item` 事件邮件还会附带附件：文章原文件（`local_folder` 源，PDF/docx/txt/md/html）与内嵌图表图片。附件读取复用文件服务的路径校验防穿越；单文件超 10MB 或不存在时跳过该附件并记日志，不中断推送。`aggregate` 事件无附件。

## PDF 正文抽取（OCR 兜底）

`local_folder` 源的 PDF 正文抽取优先读取**文本层**（PyMuPDF `page.get_text()`）。对**扫描件/图片型 PDF**（无文本层）或**字体编码损坏的 PDF**（缺 `ToUnicode CMap`），文本层会返回空串或乱码，导致 LLM 收到"无意义编码字符串"无法分析。

为此系统启用 **OCR 兜底**：当文本层质量不达标（为空、过短、或可读字符占比低于阈值）时，把 PDF 页面渲染成图片，逐页调用 NAS 本地 OCR 服务（基于 ollama / `glm-ocr`，CLAUDE.md 架构要求 5）提取正文文本，作为 `InfoItem.content` 落库。抽取流程保持"先抽取、后分析"，分析侧无感知。

- **抽取来源**记录在 `InfoItem.extraction_method`：`text_layer`（文本层可用）/ `ocr_service`（OCR 兜底成功）/ `none`（均未产出有效文本）；历史条目可能为 `vision_llm`（旧视觉 LLM 兜底，兼容保留），并在分析结果接口只读返回，便于追溯。
- **优雅降级**：OCR 兜底未启用、OCR 服务未配置、或调用失败/超时时，记录警告并保留原文本层内容，不中断同步或分析。
- **历史回补**：`extraction_method='none'` 或 `content` 为空的历史条目，会在同步 backfill 与手动重抽（`POST /api/info-sources/{source_id}/items/{item_id}/reextract`）时自动重新走"文本层 + OCR 兜底"。
- **部署注意**：OCR 兜底依赖 `ocr` 配置块指向可用的本地 OCR 服务；模型（`glm-ocr`）由服务自管，`extraction.vision_model` 已废弃（保留键以向后兼容）。glm-ocr 首次推理冷启动较慢，默认 `ocr.timeout_seconds=120`，必要时可调大。兜底按页调用，受 `max_ocr_pages` 上限约束。

## 本地 OCR / 翻译服务

系统对接 NAS 上两套本地服务（CLAUDE.md 架构要求 4/5），均通过 `Authorization: Bearer <api_key>` 鉴权，地址/密钥在 `config/app.json` 的 `ocr` / `translate` 配置块中维护，支持 `ISAS_OCR_*` / `ISAS_TRANSLATE_*` 环境变量覆盖；IP 不通时可改公网域名（`https://ocr.yuan-xin.top` / `https://translate.yuan-xin.top`）。两服务的 `api_key` 在「系统配置」页脱敏只读展示。

- **OCR 服务**（`ocr` 块，`POST /v1/ocr`，`glm-ocr`）：用于上文 PDF OCR 兜底，逐页上传渲染图片识别文本。客户端 `OCRClient` 位于 `src/app/backend/services/clients/ocr_client.py`。
- **翻译服务**（`translate` 块，`POST /v1/translate`，`translategemma`）：本轮仅提供客户端与配置（`TranslationClient`），尚未接入业务流程，供后续翻译需求（如分析前外文内容翻译）集成。支持 `source`/`target`（默认 `zh-Hans`）/`mode`（`quality`/`fast`）/`format`（`text`/`markdown`）参数。

## 配置

主配置文件 `config/app.json`，支持 `ISAS_*` 环境变量覆盖。本地 OCR / 翻译服务及抽取相关配置项：

| 配置项 | 默认值 | 环境变量 | 说明 |
|---|---|---|---|
| `figures_dir` | `data/figures`（即 `data_dir/figures`） | `ISAS_FIGURES_DIR` | 内嵌图表落盘根目录，启动时自动创建 |
| `max_figures_per_item` | `20` | `ISAS_MAX_FIGURES_PER_ITEM` | 单文件图表抽取上限，超出截断并记日志 |
| `ocr.base_url` | `http://192.168.0.100:11980` | `ISAS_OCR_BASE_URL` | NAS 本地 OCR 服务地址（`POST /v1/ocr`，`glm-ocr`） |
| `ocr.api_key` | （部署时填写） | `ISAS_OCR_API_KEY` | OCR 服务 Bearer 鉴权密钥 |
| `ocr.timeout_seconds` | `120` | `ISAS_OCR_TIMEOUT` | OCR 单次调用超时（glm-ocr 冷启动较慢，必要时调大） |
| `ocr.mode` | `text` | `ISAS_OCR_MODE` | OCR 识别模式（`text`/`markdown`/`table`/`formula`） |
| `ocr.language` | `auto` | `ISAS_OCR_LANGUAGE` | OCR 语言提示 |
| `translate.base_url` | `http://192.168.0.100:11880` | `ISAS_TRANSLATE_BASE_URL` | NAS 本地翻译服务地址（`POST /v1/translate`，`translategemma`） |
| `translate.api_key` | （部署时填写） | `ISAS_TRANSLATE_API_KEY` | 翻译服务 Bearer 鉴权密钥 |
| `translate.timeout_seconds` | `60` | `ISAS_TRANSLATE_TIMEOUT` | 翻译单次调用超时 |
| `translate.default_target` | `zh-Hans` | `ISAS_TRANSLATE_DEFAULT_TARGET` | 默认目标语言 |
| `translate.default_mode` | `quality` | `ISAS_TRANSLATE_DEFAULT_MODE` | 默认翻译模式（`quality`/`fast`） |
| `extraction.vision_fallback` | `true` | `ISAS_EXTRACTION_VISION_FALLBACK` | 是否启用 PDF OCR 兜底抽取 |
| `extraction.vision_model` | `""` | `ISAS_EXTRACTION_VISION_MODEL` | **已废弃**（OCR 模型由服务自管）；保留键以向后兼容，不再读取 |
| `extraction.max_ocr_pages` | `10` | `ISAS_EXTRACTION_MAX_OCR_PAGES` | 单文件 OCR 兜底最大渲染页数，超出截断并记日志 |
| `extraction.min_text_length` | `50` | `ISAS_EXTRACTION_MIN_TEXT_LENGTH` | 文本层可读非空白字符数下限，低于则判定不可用 |
| `extraction.readable_ratio` | `0.6` | `ISAS_EXTRACTION_READABLE_RATIO` | 文本层可读字符占比阈值，低于则判定不可用 |
| `extraction.render_dpi` | `150` | `ISAS_EXTRACTION_RENDER_DPI` | OCR 兜底页面渲染 DPI（清晰度与调用成本平衡） |

## 部署

### 三页合一迁移

升级到三页合一版本时，`init_db()` 在启动时自动执行一次性幂等迁移（`_migrate_consolidate_task_analysis`）：

- 把遗留多任务推送规则（`task_ids` 数组）按任务拆分为 1:1 推送配置（水位线原样复制，`AnalysisResult.id` 全局单调保证正确）；
- 按 `task_id` 收敛多余定时任务至最新一条；
- 曾持有 `scheduled_jobs`/`push_management` 页面权限的用户补授 `analysis_tasks`；
- 创建 `scheduled_jobs.task_id`、`push_rules.task_id` 唯一索引。

迁移**不可逆**（旧多任务语义已拆分）。**升级前务必备份 `data/app.sqlite3`**，以便回滚。迁移幂等，重复启动无副作用。

### 存量回填

首次部署后，对现有 `local_folder` 信息源触发一次同步（同步会补齐存量元数据/图表，并对 `extraction_method='none'` 或 `content` 为空的历史条目重新走视觉兜底），或对单个文件调用 `POST /api/info-sources/{source_id}/items/{item_id}/reextract` 手动重新抽取。重抽后该条目 `analyzed` 置回 False，下次分析任务会自动重新分析。
