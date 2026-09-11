## 1. LLM 客户端：输出有效性校验

- [x] 1.1 在 `services/analysis/llm_client.py` 增加 `MIN_MAX_TOKENS = 4096`、`MAX_TOKENS_RETRY_CAP = 32000` 常量与 `LLMTruncatedError(LLMError)` 异常
- [x] 1.2 `__init__` 对 `max_tokens` 施加安全下限：低于下限时按 4096 生效并记 WARNING
- [x] 1.3 把 `_post_chat` 拆为 `_request_once(messages, max_tokens)`（超时重试一次 + 状态码/格式校验，返回 `choices[0]`）
- [x] 1.4 `_post_chat` 实现校验：`finish_reason == "length"` 时以 `min(max_tokens × 2, 32000)` 重试一次，仍截断则抛 `LLMTruncatedError`
- [x] 1.5 `_post_chat` 实现空内容处理：`content` 为空时回退 `reasoning_content` 并记 WARNING，两者皆空则抛 `LLMError`（异常文案指向 `llm.max_tokens` / `llm.timeout_seconds`）

## 2. 分析引擎：逐条容错与状态判定

- [x] 2.1 新增 `_call_llm(llm, system, user, db, run_id, label)`：捕获 `LLMError` 记 WARNING 返回 `None`；再校验返回值非空（纵深防御）
- [x] 2.2 custom 模式调用点改用 `_call_llm`，失败条目跳过并计数
- [x] 2.3 aggregate 调用点改用 `_call_llm`，失败时不落库、不置 `analyzed`、不推进水位线，按覆盖条目数计入失败
- [x] 2.4 per_item 调用点改用 `_call_llm`，失败条目跳过并计数，成功的 `id` 收进 `ok_ids`
- [x] 2.5 per_item 水位线改为 `if ok_ids: ts.last_analyzed_item_id = max(ok_ids)`；aggregate 仅在成功时推进
- [x] 2.6 收尾逻辑：`run.summary` 追加失败数量；`failed_count and total_results == 0` 时置 `run.status = "failed"` 并写 `run.error`；`ScheduledJob.last_run_status` 写回真实状态
- [x] 2.7 推送钩子改由局部标志位 `analysis_ok` 守卫（仅在状态为 `succeeded` 时为 `True`）

## 3. 配置

- [x] 3.1 `config/app.json` 的 `llm.max_tokens` 由 2000 改为 16000
- [x] 3.2 `core/config.py` 的 `llm.max_tokens` 默认回退值由 2000 改为 16000

## 4. 测试

- [x] 4.1 扩展 `tests/unit/test_llm_client.py` 的 `captured` fixture，支持按调用次序返回不同响应（`resps` 列表）与自定义 client 参数
- [x] 4.2 用例：空串 / 纯空白 / 缺 `content` 键 → 抛 `LLMError`
- [x] 4.3 用例：`reasoning_content` 回退
- [x] 4.4 用例：截断 → 以翻倍 `max_tokens` 重试一次并成功返回；两次均截断 → 抛 `LLMTruncatedError`；重试预算受 `MAX_TOKENS_RETRY_CAP` 约束
- [x] 4.5 用例：`max_tokens` 低于下限被抬到 4096；高于下限原样发出
- [x] 4.6 新增 `tests/unit/test_engine_llm_failure.py`：中间条目失败 → 跳过且运行仍 `succeeded`、水位线按成功条目计算、WARNING 含条目 id
- [x] 4.7 用例：批次尾部失败 → 水位线严格小于失败条目 `id`，下次增量重跑恰好该条
- [x] 4.8 用例：全部条目失败 / 空输出 / aggregate 失败 → 运行 `failed`、无结果、水位线不动、**推送钩子未被调用**
- [x] 4.9 回归：aggregate 成功路径与 custom 模式部分失败路径行为不变
- [x] 4.10 全量测试套件通过（`python -m pytest -q`）

## 5. 文档

- [x] 5.1 README「配置」章节补充 `llm.max_tokens` 说明与部署侧需手工同步的提示
- [x] 5.2 更新需求规格说明书（分析输出校验相关 FR）
- [x] 5.3 更新设计说明书（`llm_client.py` 校验与重试、引擎失败处理与水位线语义）

## 6. 交付

- [x] 6.1 提交并推送到 GitHub `main` 分支（`738a14b`）
- [x] 6.2 触发 Jenkins 手工构建完成部署（构建 #56，部署成功，健康检查 OK）
- [x] 6.3 部署后把部署侧 `config/app.json` 的 `llm.max_tokens` 同步为 16000（或设 `ISAS_LLM_MAX_TOKENS=16000`）并重启

  2026-09-11 执行（用户授权后）：

  - 先确认 `config/env.local` 只设了 `ISAS_LLM_BASE_URL/API_KEY/MODEL/TIMEOUT`，**未设** `ISAS_LLM_MAX_TOKENS`，故该值由 `app.json` 决定。
  - 备份 `config/app.json` 到部署目录**之外**（`/opt/InformationSmartAnalysisSystem-config-backups/app.json.20260911-215321`）——部署目录内会被下次 `rsync --delete` 清掉。
  - `llm.max_tokens` 2000 → 16000，`stop.sh` + `start.sh` 重启。
  - 验证：PID 1067549 → 1076927（配置已重载），`/api/health` 返回 `{"status":"ok"}`；新 SSH 会话复查进程存活正常；部署侧配置层实测 `llm_max_tokens = 16000`。
