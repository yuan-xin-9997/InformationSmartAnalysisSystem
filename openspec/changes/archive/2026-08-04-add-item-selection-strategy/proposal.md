## Why

用户希望实现「每天定时从给定信息源选一篇未分析文章（文章时间或文件更新时间最新的）进行分析，完成后邮件推送」。经核实，系统已具备信息源同步、定时调度（APScheduler cron）、LLM 分析引擎、邮件推送（`on_run` 钩子）等能力，且 `InfoItem` 已有 `published_at`/`article_published_at`/`fetched_at` 时间字段与 `analyzed` 状态字段。唯一缺口在分析引擎的条目选择逻辑：当前固定为「按入库 `id` 升序、水位线之后取最旧篇」（`engine.py:111-114`），方向与「取时间最新」相反，且无法按文章时间排序。本变更新增可配置的条目选择策略以补齐该缺口，使用户无需改代码即可串联起「每日定时分析最新文章 + 邮件推送」的端到端流程。

## What Changes

- 新增分析任务级配置项 `selection_strategy`（存于 `AnalysisTask.config` JSON），取值：
  - `sequential`（默认，保持现状）：增量模式按 `id > last_analyzed_item_id` 水位线升序取；全量模式取全部。行为与现状完全一致。
  - `newest_unanalyzed`（新增）：按 `analyzed == False` 筛选，按 `COALESCE(published_at, article_published_at, fetched_at)` 降序取最新 N 篇（N = `max_items_per_source`，默认 50），不依赖水位线作为筛选条件。
- 后端 `src/app/backend/services/analysis/engine.py` 的非自定义（`per_item`/`aggregate`）条目选择分支按策略分流；`newest_unanalyzed` 下分析完成后仍更新 `task_sources.last_analyzed_item_id`/`last_analyzed_at`（供监控展示），但不将其作为筛选条件。
- 前端 `src/app/frontend/src/views/AnalysisTasks.vue` 表单新增「条目选择策略」下拉（顺序分析 / 最新未分析优先），值写入 `config.selection_strategy`；与现有「高级配置 JSON」兼容（保存时合并入 `config`，编辑时从 `config.selection_strategy` 回填，缺省为 `sequential`）。
- 文档：`README.md`、需求规格说明书、设计说明书补充选择策略说明，并给出「每日定时分析最新文章 + 邮件推送」的端到端配置指引。
- 不引入新依赖；不改变现有任务默认行为（向后兼容）；`Jenkinsfile` 无依赖/启动变化。

## Capabilities

### New Capabilities
- `analysis-item-selection`: 分析任务从绑定信息源中选择待分析条目的策略--支持「顺序分析」（默认，按入库顺序以水位线推进）与「最新未分析优先」（按文章时间/文件更新时间倒序选取未分析篇），以及策略在分析引擎中的执行语义与时间字段优先级。

### Modified Capabilities
<!-- 现有 specs（analysis-result-presentation / event-push / item-selection-modal）均不涉及条目选择策略的 spec 级行为变更；item-selection-modal 为前端「选择条目」弹窗，与本后端选择策略正交。故无被修改的现有能力。 -->

## Impact

- **后端**：`src/app/backend/services/analysis/engine.py`（条目选择分支按 `selection_strategy` 分流，新增 `newest_unanalyzed` 查询构造）；无 API 签名/数据模型变化（`selection_strategy` 经既有 `AnalysisTask.config: dict` 传递）。
- **前端**：`src/app/frontend/src/views/AnalysisTasks.vue`（表单新增选择策略下拉、`form.selectionStrategy` 状态、保存合并与编辑回填）。
- **测试**：`tests/` 下分析引擎选择策略单测--`sequential` 回归、`newest_unanalyzed` 选取与时间字段优先级（`published_at` → `article_published_at` → `fetched_at`）、已分析篇被跳过、`max_items_per_source` 限制、多源各自独立、水位线字段更新但不参与筛选。
- **文档**：`README.md`、需求规格说明书、设计说明书。
- **依赖/部署**：无新依赖；`Jenkinsfile` 不变。
- **端到端使用**：定时任务（已有）+ `selection_strategy=newest_unanalyzed` + `max_items_per_source=1` + `on_run` 推送规则（已有）即可实现「每日定时分析一篇最新未分析文章并邮件推送」。
