## ADDED Requirements

### Requirement: 来源文件元数据抽取与存储

系统 SHALL 在 `local_folder` 信息源同步抽取文件时，除现有纯文本外，额外抽取并持久化文章元数据：文章标题、作者、作者单位、文章发布时间、文件页数。标题、作者、发布时间、页数 MUST 取自文档属性（PDF 用 PyMuPDF `doc.metadata` 与 `doc.page_count`；Word 用 python-docx `core_properties`；HTML 用 `<title>`/`<meta>`）。作者单位 MUST 优先从首页正文启发式抽取（匹配含「大学/学院/研究所/公司/实验室/Department/University/Institute」等机构关键词的行），抽取不到时 MUST 留空。`InfoItem` 模型 MUST 新增 `author`、`author_affiliation`、`article_published_at`、`page_count` 字段承载上述信息。

#### Scenario: 从 PDF 文档属性抽取标题、作者、发布时间、页数
- **WHEN** 同步一个带文档属性的 PDF 文件
- **THEN** 系统从 `doc.metadata` 与 `doc.page_count` 抽取标题、作者、创建时间、页数并写入对应 `InfoItem` 字段

#### Scenario: 作者单位从首页正文启发式抽取
- **WHEN** 一个 PDF 首页正文某行包含「大学/研究所/Department/University」等机构关键词
- **THEN** 系统将该行作为作者单位写入 `author_affiliation`

#### Scenario: 作者单位抽取不到时留空
- **WHEN** 文档属性无作者单位且首页正文未匹配到机构关键词
- **THEN** 系统 `author_affiliation` 留空，不报错，其余元数据正常写入

#### Scenario: 无文档属性的格式回退文件名
- **WHEN** 文件为 txt/md 等无文档属性的格式
- **THEN** 系统标题回退为文件名，作者/作者单位/发布时间/页数留空，文本抽取仍照常进行

### Requirement: 正文内嵌图表抽取与存储

系统 SHALL 在抽取 `local_folder` 文件时，提取 PDF（PyMuPDF `get_images`/`extract_image`）与 Word（python-docx 内嵌图片部件）中的内嵌位图，按「年/月/日」存放于 `data` 目录下，并通过 `InfoItemFigure` 记录归属 `InfoItem`、序号、存储路径、MIME、宽高。系统 MUST NOT 引入新的图像处理依赖（以原始字节存储与服务）。单文件图表数量 MUST 受可配置上限约束，超限时截断并记录。

#### Scenario: 提取 PDF 内嵌图片并落盘
- **WHEN** 同步一个含 3 张内嵌图片的 PDF
- **THEN** 系统提取这 3 张图片，按年/月/日存入 `data` 目录，并写入 3 条 `InfoItemFigure` 记录

#### Scenario: 无内嵌图片时不创建图表记录
- **WHEN** 同步一个不含内嵌图片的文件
- **THEN** 系统不为该 `InfoItem` 创建任何 `InfoItemFigure` 记录

#### Scenario: 图表数量超上限时截断并记录
- **WHEN** 文件内嵌图片数超过配置上限
- **THEN** 系统只保存前 N 张并在日志记录已截断

### Requirement: 分析结果接口携带来源文件信息

`GET /api/analysis-tasks/{task_id}/results` 返回的 `AnalysisResultOut` SHALL 对 `per_item` 结果额外携带来源文件信息：文件名、文件路径、文章标题、作者、作者单位、发布时间、页数，以及图表列表（含可访问的图表预览地址与序号），通过关联 `InfoItem` 一次性返回。`aggregate` 结果无单一来源文件，上述文件相关字段 MUST 留空。

#### Scenario: per_item 结果返回来源文件信息与图表
- **WHEN** 前端请求某次运行的 `per_item` 分析结果
- **THEN** 每条结果携带对应 `InfoItem` 的文件名、路径、标题、作者、作者单位、发布时间、页数及图表列表

#### Scenario: aggregate 结果不返回文件相关字段
- **WHEN** 前端请求某次运行的 `aggregate` 分析结果
- **THEN** 该结果的文件名/路径/元数据/图表字段为空

#### Scenario: 单次取数即可渲染三段内容
- **WHEN** 前端打开分析结果页并展开某次运行
- **THEN** 一次 results 接口调用即可获得文件信息、文章元数据、图表与分析文本，无需额外逐条请求

### Requirement: 源文件与图表的安全访问与预览

系统 SHALL 提供 `GET /api/info-sources/{source_id}/items/{item_id}/file` 接口，按 `InfoItem` 归属校验后服务源文件，实现点击文件名在网页预览：PDF MUST 以 `inline` 方式返回（浏览器原生预览）；HTML/txt/md MUST 以可渲染文本返回；docx MUST 提供下载并附带已抽取纯文本预览。系统 SHALL 提供 `GET /api/info-sources/{source_id}/items/{item_id}/figures/{index}` 服务图表图片。上述接口 MUST 仅服务属于该 `source_id` 的 `InfoItem` 对应的文件/图表，MUST 拒绝路径穿越（不得接受任意路径参数直接读盘）。

#### Scenario: 点击 PDF 文件名在网页内嵌预览
- **WHEN** 用户在结果页点击一个 PDF 文件的文件名
- **THEN** 系统以 `inline` 方式返回该 PDF，浏览器在页面内嵌预览其内容

#### Scenario: 点击 docx 文件名提供下载与纯文本预览
- **WHEN** 用户点击一个 docx 文件的文件名
- **THEN** 系统提供该 docx 下载，并在页面展示已抽取的纯文本预览

#### Scenario: 按序号获取图表图片
- **WHEN** 前端请求某 `InfoItem` 的第 2 张图表
- **THEN** 系统返回该图表图片字节及正确 MIME

#### Scenario: 拒绝路径穿越与归属不符访问
- **WHEN** 请求尝试通过路径参数访问 `InfoItem` 归属之外的文件（如 `../` 或任意绝对路径）或跨源访问
- **THEN** 系统返回 403/404，不读取也不返回该文件

#### Scenario: 文件在磁盘缺失时返回明确错误
- **WHEN** `InfoItem` 记录存在但对应磁盘文件已被删除
- **THEN** 系统返回明确的 404 错误而非静默失败

### Requirement: 分析结果页三段式呈现

分析结果页（`TaskResults.vue`）SHALL 将每条 `per_item` 结果呈现为三段：① 文件信息（文件名 + 文件路径，文件名可点击触发网页预览）；② 文章基本信息（标题、作者、作者单位、发布时间、页数）与正文图表（缩略图可查看大图）；③ 文字分析结果（LLM `content`，markdown 渲染）。`aggregate` 结果 SHALL 保持仅展示文字分析结果。展示时间 MUST 为北京时间。

#### Scenario: per_item 结果三段式展示
- **WHEN** 用户展开一个含 `per_item` 结果的运行
- **THEN** 每条结果依次展示文件信息（可点击预览）、文章基本信息与图表、最后是文字分析结果

#### Scenario: aggregate 结果仅展示文字
- **WHEN** 用户展开一个含 `aggregate` 结果的运行
- **THEN** 该结果只展示文字分析结果，不显示文件信息与文章元数据

#### Scenario: 点击文件名打开预览
- **WHEN** 用户在某条 `per_item` 结果中点击文件名
- **THEN** 页面打开文件预览（PDF 内嵌 / HTML·txt·md 渲染 / docx 下载+文本预览）

#### Scenario: 图表缩略图可查看大图
- **WHEN** 用户点击某条结果的图表缩略图
- **THEN** 页面展示该图表大图

### Requirement: 存量数据回填

系统 SHALL 在 `local_folder` 源下次同步时，对已有 `InfoItem` 重新抽取并补齐缺失的元数据与图表。系统 SHALL 提供 `POST /api/info-sources/{source_id}/items/{item_id}/reextract` 手动重新抽取入口，对单个文件即时补齐。

#### Scenario: 下次同步补齐存量元数据与图表
- **WHEN** 一个已存在但缺元数据/图表的 `InfoItem` 所在源被再次同步
- **THEN** 系统为其补齐作者/作者单位/发布时间/页数与内嵌图表

#### Scenario: 手动重新抽取单个文件
- **WHEN** 管理员对某 `InfoItem` 调用 `reextract` 接口
- **THEN** 系统立即重新抽取该文件的元数据与图表并更新记录，返回最新结果
