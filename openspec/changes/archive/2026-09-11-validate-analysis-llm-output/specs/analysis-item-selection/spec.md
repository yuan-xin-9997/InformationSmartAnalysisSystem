## MODIFIED Requirements

### Requirement: 顺序分析策略保持现状

`sequential` 策略 SHALL 保持现有条目选择行为：增量模式下从绑定信息源选取 `id` 大于 `task_sources.last_analyzed_item_id` 的条目，按 `id` 升序、限制 `max_items_per_source` 条；全量模式下取该源全部条目按 `id` 升序、受 `max_items_per_source` 限制。

分析完成后，系统 SHALL 仅将 `last_analyzed_item_id` 推进至本批**成功产出分析结果**的条目中的最大 `id`，并相应更新 `last_analyzed_at`。分析失败的条目 MUST NOT 被计入水位线推进，MUST NOT 被置 `analyzed = True`，并 SHALL 在任务日志中以 WARNING 记录其条目 `id`、在运行摘要中计入失败条目数。这样，当失败条目集中在批次尾部（其 `id` 大于本批成功条目的最大 `id`）时，下一次 `sequential` 增量运行会重新选中并重试它们。

若本批**全部**条目分析失败，系统 MUST NOT 推进 `last_analyzed_item_id`，也 MUST NOT 更新 `last_analyzed_at`。

#### Scenario: 增量模式按水位线升序取
- **WHEN** `sequential` 增量运行且 `last_analyzed_item_id=10`、`max_items_per_source=5`
- **THEN** 选取 `id > 10` 的条目中 `id` 最小的 5 条，按 `id` 升序

#### Scenario: 全量模式取全部受上限限制
- **WHEN** `sequential` 全量运行且 `max_items_per_source=50`、源中有 80 条
- **THEN** 选取该源全部条目按 `id` 升序的前 50 条

#### Scenario: 分析后推进水位线
- **WHEN** `sequential` 策略分析完一批条目且全部成功
- **THEN** `last_analyzed_item_id` 更新为本批成功条目的最大 `id`

#### Scenario: 部分条目失败时水位线只到成功条目
- **WHEN** `sequential` 策略分析一批条目，其中 `id=7` 的条目分析失败，其余（最大 `id=9`）成功
- **THEN** `last_analyzed_item_id` 更新为 9，`id=7` 的条目不被置为已分析，任务日志记录含条目 `id=7` 的 WARNING，运行摘要计入 1 条失败

#### Scenario: 失败条目位于批次尾部时可被下次增量重试
- **WHEN** `sequential` 增量批次中 `id` 最大的条目分析失败，其余成功，水位线推进至次大的成功条目 `id`
- **THEN** 下一次 `sequential` 增量运行选取 `id` 大于该水位线的条目，从而重新选中该失败条目

#### Scenario: 本批全部失败时不推进水位线
- **WHEN** `sequential` 策略一批条目全部分析失败
- **THEN** `last_analyzed_item_id` 与 `last_analyzed_at` 均保持不变
