## ADDED Requirements

### Requirement: 分析任务支持配置条目选择策略

分析任务 SHALL 支持在 `config.selection_strategy` 中配置条目选择策略，取值为 `sequential`（默认）或 `newest_unanalyzed`。未指定 `selection_strategy` 或值为非已知取值时 SHALL 回退到 `sequential` 且不报错。策略 SHALL 在非自定义模式（`per_item` / `aggregate`）下生效；自定义模式（`custom`）SHALL 不受策略影响，仍仅分析 `config.custom_item_ids` 指定的条目。

#### Scenario: 未指定策略时默认顺序分析
- **WHEN** 分析任务 `config` 未包含 `selection_strategy`
- **THEN** 分析引擎按 `sequential` 策略选择条目，行为与现状一致

#### Scenario: 未知策略值回退默认
- **WHEN** `config.selection_strategy` 为非已知取值（如 `"random"`）
- **THEN** 系统回退到 `sequential` 策略，不报错

#### Scenario: 自定义模式不受策略影响
- **WHEN** 任务 `config.mode` 为 `custom` 且 `selection_strategy` 为 `newest_unanalyzed`
- **THEN** 引擎仍仅分析 `custom_item_ids` 指定条目，策略不改变候选集

### Requirement: 顺序分析策略保持现状

`sequential` 策略 SHALL 保持现有条目选择行为：增量模式下从绑定信息源选取 `id` 大于 `task_sources.last_analyzed_item_id` 的条目，按 `id` 升序、限制 `max_items_per_source` 条；全量模式下取该源全部条目按 `id` 升序、受 `max_items_per_source` 限制。分析完成后 SHALL 将 `last_analyzed_item_id` 推进至本批最大 `id`。

#### Scenario: 增量模式按水位线升序取
- **WHEN** `sequential` 增量运行且 `last_analyzed_item_id=10`、`max_items_per_source=5`
- **THEN** 选取 `id > 10` 的条目中 `id` 最小的 5 条，按 `id` 升序

#### Scenario: 全量模式取全部受上限限制
- **WHEN** `sequential` 全量运行且 `max_items_per_source=50`、源中有 80 条
- **THEN** 选取该源全部条目按 `id` 升序的前 50 条

#### Scenario: 分析后推进水位线
- **WHEN** `sequential` 策略分析完一批条目
- **THEN** `last_analyzed_item_id` 更新为本批最大 `id`

### Requirement: 最新未分析优先策略选取时间最新的未分析篇

`newest_unanalyzed` 策略 SHALL 从绑定信息源选取 `analyzed == False` 的条目，按时间倒序（最新在前）排列，限制 `max_items_per_source` 条。该策略 MUST NOT 使用 `last_analyzed_item_id` 作为候选筛选条件。分析完成后 SHALL 将选中条目置 `analyzed = True`，并 SHALL 更新 `last_analyzed_item_id` 与 `last_analyzed_at`（供监控展示），但该水位线 MUST NOT 影响下次 `newest_unanalyzed` 的候选筛选。

#### Scenario: 选取时间最新的未分析篇
- **WHEN** `newest_unanalyzed` 策略运行，源中未分析条目 A（发布时间 7月28日）、B（发布时间 7月29日），另有已分析条目 C（发布时间 7月30日），`max_items_per_source=1`
- **THEN** 选取 B（未分析中时间最新），并将其置为已分析

#### Scenario: 已分析篇被跳过
- **WHEN** `newest_unanalyzed` 策略运行
- **THEN** `analyzed == True` 的条目不出现在候选集中

#### Scenario: 限制选取数量
- **WHEN** `newest_unanalyzed` 策略、`max_items_per_source=1`、源中有 3 篇未分析
- **THEN** 仅选取时间最新的 1 篇

#### Scenario: 水位线不参与候选筛选
- **WHEN** `newest_unanalyzed` 策略运行且 `last_analyzed_item_id=100`，存在 `id < 100` 的未分析条目
- **THEN** 这些 `id < 100` 的未分析条目仍可被选中，不被水位线排除

#### Scenario: 分析后水位线更新但不影响下次候选
- **WHEN** `newest_unanalyzed` 策略分析完一篇 `id=5` 的条目
- **THEN** `last_analyzed_item_id` 更新为 5，但下次运行仍按 `analyzed == False` + 时间倒序选取，不依据 `id > 5`

### Requirement: 时间排序字段优先级

`newest_unanalyzed` 策略的排序时间键 SHALL 为 `COALESCE(published_at, article_published_at, fetched_at)`，按此优先级取首个非空值，并按降序排列（最新在前）。时间键完全相同或均为空时 SHALL 按 `id` 降序作为次级排序以保证结果稳定。

#### Scenario: 优先使用文章发布时间
- **WHEN** 两条未分析条目均有 `published_at`
- **THEN** 按 `published_at` 降序排列

#### Scenario: published_at 缺失回退文档元数据时间
- **WHEN** 条目 `published_at` 为空且 `article_published_at` 非空
- **THEN** 排序键取 `article_published_at`

#### Scenario: 文章时间均缺失回退入库时间
- **WHEN** 条目 `published_at` 与 `article_published_at` 均为空、`fetched_at` 非空（如 website 源条目）
- **THEN** 排序键取 `fetched_at`

#### Scenario: 时间键相同按 id 降序稳定排序
- **WHEN** 两条未分析条目的时间键取值相同
- **THEN** 按 `id` 降序排列

### Requirement: 前端配置条目选择策略

分析任务表单 SHALL 提供「条目选择策略」下拉控件，选项为「顺序分析」（值 `sequential`）与「最新未分析优先」（值 `newest_unanalyzed`）。保存时 SHALL 将下拉所选值写入 `config.selection_strategy`，并覆盖「高级配置 JSON」中可能存在的同名键。编辑已有任务时 SHALL 从 `config.selection_strategy` 回填下拉，缺省显示「顺序分析」。

#### Scenario: 下拉选择写入 config
- **WHEN** 用户在表单下拉选择「最新未分析优先」并保存
- **THEN** 任务 `config.selection_strategy` 等于 `"newest_unanalyzed"`

#### Scenario: 编辑已有任务回填下拉
- **WHEN** 打开一个 `config.selection_strategy="newest_unanalyzed"` 的任务进行编辑
- **THEN** 下拉显示「最新未分析优先」

#### Scenario: 未设置策略时回填默认
- **WHEN** 打开一个未设置 `selection_strategy` 的任务进行编辑
- **THEN** 下拉显示「顺序分析」
