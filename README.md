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

## 配置

主配置文件 `config/app.json`，支持 `ISAS_*` 环境变量覆盖。本次新增配置项：

| 配置项 | 默认值 | 环境变量 | 说明 |
|---|---|---|---|
| `figures_dir` | `data/figures`（即 `data_dir/figures`） | `ISAS_FIGURES_DIR` | 内嵌图表落盘根目录，启动时自动创建 |
| `max_figures_per_item` | `20` | `ISAS_MAX_FIGURES_PER_ITEM` | 单文件图表抽取上限，超出截断并记日志 |

## 部署

### 存量回填

首次部署后，对现有 `local_folder` 信息源触发一次同步（同步会补齐存量元数据/图表），或对单个文件调用 `POST /api/info-sources/{source_id}/items/{item_id}/reextract` 手动重新抽取。
