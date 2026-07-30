## Why

分析任务页（`AnalysisTasks.vue`）在「自定义（指定条目）」模式下点击「选择条目」打开的弹窗，目前是一个纯 HTML 表格，按 `id` 倒序分页展示条目，仅有一个「已分析」筛选下拉。两个痛点：(1) 已选条目散落在不同分页中，用户无法一眼看到本次已选了哪些、也无法集中取消选择；(2) 无法按标题/发布时间等列排序，也无法按标题关键词筛选，条目多时定位困难。本次增强让已选条目前排集中展示，并支持按列排序与筛选，提升指定条目场景的选择效率与可核验性。

## What Changes

- **已选条目前排置顶**：弹窗顶部新增「已选条目」区，始终展示当前所有已选条目（无论当前筛选/排序条件如何），每条提供取消选择控件；下方「可浏览列表」排除已选条目以避免重复。在可浏览列表中勾选即将其移入顶部已选区，在已选区取消即将其移回可浏览列表，两区实时同步。
- **列排序**：可浏览列表的「标题 / 已分析 / 发布时间」列表头可点击排序，支持升/降序切换，排序状态在表头以箭头指示；排序为服务端排序，跨分页一致。
- **列筛选**：在现有「已分析」筛选基础上，新增「标题关键词」模糊筛选；筛选与排序可组合，共同作用于可浏览列表。已选条目区不受筛选影响，始终可见。
- **后端查询接口扩展**：`POST /api/info-sources/items/query` 增加可选参数 `ids`、`exclude_ids`、`sort_by`、`order`、`keyword`，分别支持按 ID 取已选、排除已选、按白名单字段排序、标题模糊匹配；向后兼容（现有调用不传新参数时行为不变），并对排序字段做白名单校验防注入。
- **不引入新依赖**：沿用现有 Vue 3 + 原生 HTML/CSS 与 SQLAlchemy，不引入 UI 库或前端表格组件。
- **范围限定**：仅改动 `AnalysisTasks.vue` 的「选择条目」弹窗与共享的后端查询接口；`InfoSources.vue` 的同类条目浏览弹窗不在本次范围（因后端扩展向后兼容，其行为不受影响）。

## Capabilities

### New Capabilities
- `item-selection-modal`: 分析任务页「自定义（指定条目）」模式下「选择条目」弹窗的增强--已选条目前排置顶展示、按列排序、按列筛选，以及支撑这些能力的服务端查询接口扩展。

### Modified Capabilities
<!-- 现有 specs 仅有 event-push，与本变更无关；本变更为新增能力，无被修改的现有能力。 -->

## Impact

- **前端**（`src/app/frontend/src/views/AnalysisTasks.vue`）：重构「选择条目」弹窗--新增「已选条目」区与取消选择控件、列头点击排序（含升降序指示）、标题关键词筛选输入、`pickerSelected` 状态及其与 `form.custom_item_ids` 的同步与取数联动；`src/app/frontend/src/api/sources.ts` 的 `queryItemsApi` 及请求/响应类型扩展 `ids`/`exclude_ids`/`sort_by`/`order`/`keyword`。
- **后端**（`src/app/backend/schemas/info_source.py`）：`ItemsQueryRequest` 增加可选字段 `ids`/`exclude_ids`/`sort_by`/`order`/`keyword`；（`src/app/backend/api/info_sources.py`）`query_items` 实现按 ID 过滤、排除已选、按白名单字段服务端排序、标题 `ilike` 模糊匹配，保留现有 `analyzed` 过滤与分页。
- **测试**：后端 `query_items` 各新参数单测（排序白名单与注入防护、`keyword` 模糊匹配、`ids`/`exclude_ids` 组合、不传新参数的向后兼容）；前端 `npm run build` 冒烟 + 手工验证置顶/排序/筛选交互。
- **文档**：更新 `README.md`、需求规格说明书、设计说明书；`Jenkinsfile` 无依赖/启动变化则不动。
