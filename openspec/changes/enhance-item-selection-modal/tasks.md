## 1. 后端 Schema 扩展

- [x] 1.1 在 `src/app/backend/schemas/info_source.py` 的 `ItemsQueryRequest` 增加可选字段 `ids: list[int] | None = None`、`exclude_ids: list[int] | None = None`、`sort_by: str | None = None`、`order: Literal["asc", "desc"] = "desc"`、`keyword: str | None = None`
- [x] 1.2 编写测试：`ItemsQueryRequest` 解析新字段、默认值正确、不传新参数时与旧结构兼容（测试先行）

## 2. 后端 query_items 重构与扩展

- [x] 2.1 在 `src/app/backend/api/info_sources.py` 重构 `query_items` 为单一查询链：在 SQL 层统一应用 `source_ids`/`analyzed`/`keyword`/`ids`/`exclude_ids` 过滤，删除第 64–65 行取行后的 Python 二次过滤（修复 `analyzed` 筛选时每页不足 `limit` 的缺陷）；计数与取行共用同一过滤链
- [x] 2.2 实现白名单排序：建立 `sort_by` 字段名 -> ORM 列映射（`title`/`published_at`/`analyzed`/`created_at`），未知值回退 `InfoItem.id.desc()`；`order` 控制升/降序；`sort_by=None` 时保持 `id` 倒序；`keyword` 用 `InfoItem.title.ilike(f"%{keyword}%")` 参数化绑定
- [x] 2.3 编写测试：`ids` 取指定条目、`exclude_ids` 排除、`sort_by`+`order` 各字段排序、`keyword` 模糊匹配（大小写不敏感）、白名单外字段回退默认、不传新参数向后兼容、`analyzed` 筛选每页满额返回、排序字段注入防护（测试先行）

## 3. 前端 API 层扩展

- [x] 3.1 在 `src/app/frontend/src/api/sources.ts` 的 `queryItemsApi` 增加可选参数 `ids/exclude_ids/sort_by/order/keyword`（向后兼容，默认不传），扩展请求体类型
- [x] 3.2 确认 `InfoItemBrief` 接口字段覆盖弹窗所需（标题/已分析/发布时间已在），无需新增字段

## 4. 前端弹窗--已选条目前排置顶

- [x] 4.1 在 `AnalysisTasks.vue` 新增 `pickerSelected: Ref<InfoItemBrief[]>` 状态；`openPicker` 时若 `form.custom_item_ids` 非空，用 `queryItemsApi(form.source_ids, ..., { ids: form.custom_item_ids })` 一次性取已选详情填充 `pickerSelected`
- [x] 4.2 新增弹窗顶部「已选条目」区：独立表格展示已选条目（标题/已分析/发布时间）+ 每条取消选择控件；设最大高度并内部滚动；显示「已选 N 篇」计数
- [x] 4.3 改 `togglePick`：勾选时把条目对象移入 `pickerSelected` 并同步 `form.custom_item_ids`；取消时从 `pickerSelected` 移除并触发 `loadPicker()` 重取可浏览列表
- [x] 4.4 可浏览列表 `loadPicker` 携带 `exclude_ids: form.custom_item_ids`，使已选条目不在可浏览列表重复出现

## 5. 前端弹窗--列排序

- [x] 5.1 新增 `pickerSortBy: Ref<'title'|'published_at'|'analyzed'|'created_at'|null>`、`pickerSortOrder: Ref<'asc'|'desc'>` 状态；`loadPicker` 透传 `sort_by`/`order` 给 `queryItemsApi`
- [x] 5.2 表头「标题/已分析/发布时间」可点击：首次点击该列升序、再次点击切换降序；表头加 `cursor:pointer` 与 `▲/▼` 可视指示（通过 `sortable`/`sort-asc`/`sort-desc` 状态类）
- [x] 5.3 改变排序列/方向时重置到第 1 页并重取；`openPicker` 重置排序为默认（`id` 倒序）

## 6. 前端弹窗--列筛选

- [x] 6.1 新增 `pickerKeyword: Ref<string>` 与标题关键词输入框；`loadPicker` 透传 `keyword`；输入加防抖后重取并重置到第 1 页，清空时恢复
- [x] 6.2 保留现有「已分析」筛选下拉与 `onPickerFilterChange` 重置第 1 页逻辑；确认已选区独立取数（不传 `keyword`/`analyzed`），不受筛选影响

## 7. 冒烟测试与文档

- [x] 7.1 后端：运行 `query_items` 相关单测全部通过
- [x] 7.2 前端：`npm run build` 通过；手工验证已选置顶/列排序升降序/标题关键词筛选/已分析筛选组合/分页/取消选择回流的交互
- [x] 7.3 更新 `README.md`（「选择条目」弹窗已选置顶、列排序、关键词筛选说明）、需求规格说明书、设计说明书
- [ ] 7.4 `Jenkinsfile` 无依赖/启动变化则不动；提交 Github 后手工触发 Jenkins 构建并由用户验证新增功能
