## Context

分析任务页 `src/app/frontend/src/views/AnalysisTasks.vue` 在「自定义（指定条目）」模式下，点击「选择条目」按钮（行 71，仅 `form.mode === 'custom'` 时显示）打开条目选择弹窗（行 85–127）。弹窗当前实现（经代码勘探确认）：

- **纯 HTML 表格**（行 107–117），4 列：选择 / 标题 / 已分析 / 发布时间。前端为 Vue 3 + 原生 HTML/CSS，**无 UI 库**（`package.json` 仅 vue/vue-router/pinia/axios/dompurify/marked），样式来自全局 `style.css`。
- **选择状态**：仅保存 ID 数组 `form.custom_item_ids: number[]`（行 173），不缓存条目对象；`isPicked`/`togglePick`（行 333–342）操作该数组。
- **取数**：`loadPicker()`（行 290–301）调用 `queryItemsApi(source_ids, limit, offset, analyzed)` -> `POST /api/info-sources/items/query`，**服务端分页**（50/100/200）。
- **现有筛选**：仅一个「全部/已分析/未分析」下拉（行 94–98）映射到 `analyzed: bool|undefined`。
- **无任何排序**：表头无点击、无 sort 状态；后端硬编码 `order_by(InfoItem.id.desc())`（`api/info_sources.py` 行 58）。

后端 `query_items`（`api/info_sources.py` 行 41–66）现状有一个**潜在缺陷**：`analyzed` 过滤仅作用于计数用的 `base` 查询，而真正取行的 `select`（行 54–62）**未带 `analyzed` 过滤**，随后在第 64–65 行用 Python 二次过滤。这导致开启 `analyzed` 筛选时，每页返回行数可能少于 `limit`（SQL 取满页后再被 Python 剔除）。本次重构将一并修正。

约束（CLAUDE.md）：不硬编码环境信息；时间显示北京时间；`data` 目录不入 `.gitignore`；优先 SQLite/Python/FastAPI+Vue；无新依赖。现有 `InfoSources.vue`（行 66–109）有近乎复制的同类条目浏览弹窗，使用同一 `InfoItemBrief` 类型与 `queryItemsApi`，但不在本次范围。

## Goals / Non-Goals

**Goals:**
- 弹窗顶部「已选条目」区始终集中展示当前所有已选条目，可逐条取消，不受筛选/排序影响。
- 可浏览列表支持点击「标题/已分析/发布时间」列表头排序（升/降序，跨分页服务端一致）。
- 可浏览列表支持「标题关键词」模糊筛选，并与现有「已分析」筛选可组合。
- 后端 `query_items` 扩展 `ids/exclude_ids/sort_by/order/keyword` 可选参数，向后兼容，排序字段白名单防注入；顺带修复 `analyzed` 过滤的 Python 后过滤缺陷。
- 不引入新依赖。

**Non-Goals:**
- 不改动 `InfoSources.vue` 的同类弹窗（后端扩展向后兼容，其行为不变）。
- 不为排序新增暴露 `author`/`article_published_at` 等 `InfoItemBrief` 之外的字段；排序仅基于现有可见列。
- 不做发布时间日期范围筛选、不做全文检索（标题 `ilike` 已满足定位需求）。
- 不改变 `custom_item_ids` 的持久化结构与自定义分析任务的运行语义。

## Decisions

### 决策 1：已选置顶采用「独立已选区」，而非「列表内选中优先排序」
弹窗顶部新增独立「已选条目」区，始终展示全部已选条目；下方可浏览列表通过 `exclude_ids` 排除已选，避免重复。勾选可浏览列表条目即移入已选区，在已选区取消即移回可浏览列表。
**理由**：选择状态目前仅存 ID，且分页为服务端，已选条目散落各页。独立已选区保证选择集合始终可审视、可逐条取消，不受当前筛选/排序影响（筛选不应让已选条目「消失」）。
**备选**：服务端 `ORDER BY (id IN selected) DESC, <sort>` 把已选排到列表前部--被否：被筛选排除的已选条目会从列表消失，丢失选择可视性；且选中数超过页大小时已选跨页，仍不集中。

### 决策 2：已选区取数--打开时按 ID 批量取，会话内用内存对象联动
`openPicker` 时若 `form.custom_item_ids` 非空，用 `queryItemsApi(..., { ids: custom_item_ids })` 一次性取回已选条目详情填充 `pickerSelected: InfoItemBrief[]`。会话内勾选/取消直接用内存中的条目对象（勾选来自可浏览列表 `pickerItems`，取消来自 `pickerSelected`），不做逐条请求；取消后触发可浏览列表 `loadPicker()` 重取（让该条回到列表）。
**理由**：避免 N+1 与闪烁；仅打开时一次请求补齐预选详情（如编辑已存任务场景）。
**备选**：每次勾选/取消逐条请求详情--被否（N+1、卡顿）；仅展示 ID 不取详情--被否（无标题不可核验）。

### 决策 3：可浏览列表排除已选（`exclude_ids`）
可浏览列表请求携带 `exclude_ids: form.custom_item_ids`，使已选条目不重复出现在列表中。勾选时乐观地从 `pickerItems` 移除并加入 `pickerSelected`；取消时重取可浏览列表。
**理由**：两区不重复，心智模型清晰（已选区=你的选择，列表=可添加项）。
**备选**：列表中已选项显示为勾选且同时出现在已选区--被否（重复展示易混淆）。

### 决策 4：排序服务端化 + 字段白名单
`ItemsQueryRequest` 增 `sort_by: "title"|"published_at"|"analyzed"|"created_at"|None` 与 `order: "asc"|"desc"`（默认 `desc`）。后端用字段名->ORM 列的字典映射校验，未知字段回退默认 `InfoItem.id.desc()`，**不把用户输入拼入 SQL**。`sort_by=None` 时保持现状 `id` 倒序。
**理由**：服务端分页下客户端排序只会重排当前页，跨页顺序错乱；服务端排序保证一致。白名单防注入与任意列暴露。
**备选**：客户端排序--被否（跨页不一致）。

### 决策 5：筛选--标题 `ilike` 模糊匹配 + 保留已分析，统一在 SQL 层
`ItemsQueryRequest` 增 `keyword: str|None`，后端 `InfoItem.title.ilike(f"%{keyword}%")`（SQLAlchemy 参数化绑定，安全）。与 `analyzed` 一并在 SQL 层过滤。改变筛选重置到第 1 页。
**理由**：标题是主要定位字段；`ilike` 大小写不敏感包含匹配足够；SQLite 原生支持。
**备选**：FTS5 全文检索--被否（过度工程，规模不需要）。

### 决策 6：重构 `query_items` 为单一查询链
将 `base`（计数）与 `select`（取行）合并为一条带全部过滤（`source_ids`/`analyzed`/`keyword`/`ids`/`exclude_ids`）+ 排序的查询，`.count()` 取 total、`limit/offset` 取行。**顺带修复** `analyzed` 的 Python 后过滤缺陷（行 64–65 删除）。
**理由**：新参数必须在取行查询中生效才能正确分页；统一查询消除计数/取行不一致与 analyzed 缺陷。
**备选**：保留双查询并各自补参数--被否（重复且易再出错）。

### 决策 7：前端无新依赖，沿用自定义 CSS
复用 `.modal`/`.modal-card.large`/`.toolbar`/`.stats`/`.button-row`/`table,th,td`/`.pill`/`.empty.compact`/`.muted`。可排序列头加 `cursor:pointer` 与 `▲/▼` 指示（通过 `sortable` class 与 `sort-asc`/`sort-desc` 状态类）。已选区用独立 `table` + 最大高度内部滚动。
**理由**：项目约定无 UI 库（`package.json` 已确认）；与 `InfoSources.vue` 表格风格一致。
**备选**：引入 Element Plus 等表格组件--被否（违背无新依赖与现有风格）。

### 决策 8：`InfoItemBrief` 不扩展字段
可见列（标题/已分析/发布时间）已在 `InfoItemBrief` 中，排序基于这些字段即可，不新增暴露 `author`/`article_published_at`。
**理由**：最小改动面；用户需求仅涉现有列。
**备选**：为支持按作者等排序而扩展 schema--被否（超出需求，非目标）。

## Risks / Trade-offs

- **已选区条目过多撑高弹窗** -> 已选区设最大高度并内部滚动；显示「已选 N 篇」计数。
- **`exclude_ids` 列表很大时请求体膨胀** -> POST body 为 JSON，常规选择量可承受；极大量（上千）后续可优化为「已选优先排序 + 不排除」，本次不处理并记日志。
- **取消选择后重取可浏览列表，分页位置可能变化** -> 接受；保持当前页码，条目是否符合当前页由服务端决定。
- **`published_at` 含 NULL 的排序位置** -> SQLite 中 NULL 视为最小，`desc` 时 NULL 在末尾；可接受，不额外处理。
- **后端 `query_items` 重构改变 `analyzed` 过滤时机** -> 由 Python 后过滤改为 SQL 过滤，开启 `analyzed` 筛选时每页将满额返回（属缺陷修复）；在迁移说明中标注，回归测试覆盖。
- **排序字段白名单遗漏** -> 白名单仅含 4 个可见列对应字段；未知字段回退默认而非报错，前端只发送白名单内字段。

## Migration Plan

1. **后端**：`schemas/info_source.py` 的 `ItemsQueryRequest` 增可选 `ids/exclude_ids/sort_by/order/keyword`；`api/info_sources.py` 重构 `query_items` 为单一查询链并实现新参数 + 白名单排序 + analyzed 修复；单测覆盖各参数、白名单与注入防护、向后兼容。
2. **前端 API 层**：`api/sources.ts` 的 `queryItemsApi` 增可选 `ids/exclude_ids/sort_by/order/keyword` 参数（向后兼容），扩展请求类型。
3. **前端弹窗**：`AnalysisTasks.vue` 重构弹窗--新增已选区与 `pickerSelected` 状态、`openPicker` 取已选、列头排序（`pickerSortBy`/`pickerSortOrder`）、标题关键词筛选（`pickerKeyword`）、`togglePick` 联动两区、`exclude_ids` 取数；`npm run build` 冒烟 + 手工验证。
4. **文档**：更新 README、需求规格说明书、设计说明书；Jenkinsfile 无依赖/启动变化则不动。
5. **回滚**：后端新参数可选、`query_items` 重构独立可回退；前端改动隔离在弹窗与 `api/sources.ts`，回滚不影响现有任务创建/运行。

## Open Questions

- 已选区内条目排序：建议按选择顺序（最新选择在前），便于回顾；如需可按标题排序，后续可加。
- 是否同步增强 `InfoSources.vue` 同类弹窗：本次 Non-Goal，后端兼容不影响其行为；后续可统一抽取为共享组件。
