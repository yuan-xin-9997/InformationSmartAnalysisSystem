## Why

线上发出了一封**空正文邮件**：分析任务对 64KB 长文调用推理模型时，`llm.max_tokens=2000` 被思考阶段耗尽，
模型返回空 `content` 且 `finish_reason="length"`；而系统在 LLM 调用未抛异常的情况下，无条件把该结果落库、
置 `InfoItem.analyzed=True`、把 `TaskRun.status` 置为 `succeeded`，并触发 `on_analysis_completed` 推送钩子。

故障由三层缺陷叠加而成：

1. **配置**：`max_tokens=2000` 对推理模型严重不足——其 token 预算需覆盖「思考 + 回答」。
2. **客户端**：`llm_client.py` 只读 `choices[0].message.content`，不检查 `finish_reason`、
   不对 `reasoning_content` 兜底、空串照样当结果返回。
3. **引擎**：`engine.py` 的三处 LLM 调用点只要不抛异常就判成功；且推送钩子挂在 `try/except` 的
   `else` 分支上，**只判断「有没有抛异常」**——即使运行状态是 `failed` 也照样推送。

## What Changes

- **LLM 客户端输出校验**：`finish_reason == "length"` 判为输出被截断，以翻倍的 `max_tokens`
  自动重试一次（上限 32000），仍截断则抛错；`content` 为空时回退 `reasoning_content`，
  两者皆空则抛错。空内容/截断**不再可能**被当作正常结果返回。
- **max_tokens 安全下限**：代码内置下限 4096，配置值低于下限时按 4096 生效并记 WARNING。
  部署侧因 `merge_app_config.py` 只补新键而残留的陈旧值（2000）由此自动兜底。
  仓库默认值同步由 2000 提升到 16000。
- **分析引擎逐条容错**：单条分析失败（空内容/截断/超时）只跳过该条目——不落库、不置
  `analyzed`、不推进水位线——其余条目继续；运行摘要显式标注失败数量，日志以 WARNING 记录条目 ID。
- **全部失败即失败**：本次运行未产出任何有效结果时，`TaskRun.status` 置为 `failed`。
- **推送钩子收紧**：仅当运行状态为 `succeeded` 时才触发 `on_analysis_completed`，
  堵死「无异常但结果为空」这一推送路径。
- **水位线语义**：`sequential` 增量模式下 `last_analyzed_item_id` 只推进到本批**成功**条目的最大
  `id`，使集中在批次尾部的失败条目在下一次增量中被自动重跑。

## Capabilities

### New Capabilities

<!-- 无新增能力，均基于已有能力演进 -->

### Modified Capabilities

- `task-analysis-workbench`: 新增「分析输出有效性校验」要求——校验 LLM 输出非空且未被截断；
  校验不通过的条目不得落库、不得置 `analyzed`；运行状态与摘要须反映失败条目数；
  全部条目失败时运行状态为 `failed`；**推送仅在运行状态为 `succeeded` 时触发**。
- `analysis-item-selection`: 「`sequential` 条目选择策略」的水位线推进规则由「推进至本批最大 `id`」
  改为「推进至本批成功条目的最大 `id`」，并要求失败条目在日志与运行摘要中可见。
- `event-push`: 「按任务完成后自动推送（on_run）」补充场景，明确「运行无异常但全部条目分析失败
  （状态为 `failed`）」时 MUST NOT 触发推送。

## Impact

- **后端服务**：
  - `services/analysis/llm_client.py`：新增 `MIN_MAX_TOKENS` / `MAX_TOKENS_RETRY_CAP` 常量与
    `LLMTruncatedError`；`_post_chat` 拆分为 `_request_once`（超时重试 + HTTP 处理）与
    `_post_chat`（输出校验 + 截断重试）；`__init__` 施加 max_tokens 下限。
  - `services/analysis/engine.py`：新增 `_call_llm()` 统一三处调用点（custom / aggregate / per_item）
    的失败处理；per_item 水位线改按成功条目计算；`run.summary` / `run.status` / `run.error`
    反映失败；推送钩子改由局部标志位守卫；`ScheduledJob.last_run_status` 写回真实状态。
- **配置**：`config/app.json` 与 `core/config.py` 的 `llm.max_tokens` 默认值 2000 → 16000。
- **部署**：`config/app.json` 的 `llm.max_tokens` 在已部署实例上不会随流水线更新（增量合并只补新键），
  交付说明需提示运维手工同步到 16000；代码下限保证未同步时也不会再产生空正文邮件。
- **API/Schema/前端**：无变更。运行状态仍为 `succeeded`/`failed`（不引入 `partial`），
  部分成功通过 `summary` 文本表达，无需改动 `TaskCenter.vue` / `AnalysisTasks.vue`。
- **测试**：新增 `tests/unit/test_engine_llm_failure.py`（8 例）；扩展 `tests/unit/test_llm_client.py`
  （空内容、`reasoning_content` 回退、截断重试与上限、max_tokens 下限）。
- **文档**：更新 README「配置」章节、需求规格说明书、设计说明书。
