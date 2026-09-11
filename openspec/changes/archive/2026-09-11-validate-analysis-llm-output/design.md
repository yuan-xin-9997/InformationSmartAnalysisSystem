## Context

动机与问题见 `proposal.md`。设计相关现状与约束：

- `services/analysis/llm_client.py` 的 `_post_chat()` 同时承担「HTTP 请求（含超时重试一次）」与「解析响应」
  两件事，返回值直接是 `content` 字符串。生产环境中唯一的调用方是分析引擎（`chat`）；`chat_with_images`
  已无生产调用方（PDF 正文兜底改走本地 OCR 服务），仅测试使用。
- `services/analysis/engine.py` 有三处 LLM 调用点：custom 模式（逐条）、per_item（逐条）、aggregate（整源一次）。
  三处都是「调用 → 原样落库 → 置 analyzed」，没有共享的失败处理。
- 推送钩子 `on_analysis_completed(task_id)` 位于 `run_analysis` 的 `try/except` 的 `else` 分支——该分支只表示
  「未抛异常」，与 `run.status` 无关。
- 前端 `TaskCenter.vue` / `AnalysisTasks.vue` 只识别 `succeeded` / `failed`（外加 `running` / `pending`），
  引入新状态需要改前端。
- Jenkins 的 `JenkinsConfig/merge_app_config.py` 做的是「深合并、只补缺失键、保留部署侧既有值」，
  因此仓库 `config/app.json` 里调大 `llm.max_tokens` **不会**传播到已部署实例。

## Goals / Non-Goals

**Goals:**

- 空内容 / 被截断的 LLM 输出在**两层**都被拦住：客户端层判失败，引擎层再兜一次底。
- 单条失败不拖垮整批；失败在任务日志与运行摘要中可见。
- 运行状态与推送触发严格绑定：状态不是 `succeeded` 就绝不推送。
- 部署侧配置陈旧时仍有安全下限，杜绝「配置没同步 → 又发空邮件」。

**Non-Goals:**

- 不引入 `partial` 运行状态（需改前端；用 `summary` 文本表达部分成功足够）。
- 不改任务配置结构，不支持逐任务 `max_tokens` 覆盖。
- 不改 `chat_with_images` 的对外语义（无生产调用方，本次仅被动继承校验）。
- 不重构推送侧对空正文的过滤（推送的输入源已被上游保证非空）。

## Decisions

### 1. 校验放在客户端层，重试也放在客户端层

`_post_chat` 拆为 `_request_once(messages, max_tokens)`（HTTP + 超时重试 + 状态码/格式校验，返回 `choices[0]`）
与 `_post_chat(messages)`（输出校验 + 截断重试）。

- **理由**：`_request_once` 已含「超时重试一次」，截断重试叠加在它之上形成两层重试，职责清晰且与既有风格一致。
  重试放在客户端层意味着引擎不需要感知「截断」这一概念，三处调用点无需各自实现重试。
- **备选**：把截断重试放进引擎（需要给 `chat()` 加 `max_tokens` 参数并由引擎管理预算）。否决原因：
  重试逻辑会散落到三处调用点，且 `chat_with_images` 拿不到同样的保护。
- **备选**：`finish_reason == "length"` 但有非空 `content` 时「截断但可用，记警告照常返回」。否决原因：
  被截断的分析结果本身就是残缺的，推送给用户等于交付半成品；且这条路径会让「截断」在多数情况下静默通过。

### 2. 截断重试预算 = `min(max_tokens × 2, 32000)`，只重试一次

单次调用成本翻倍可接受，不设上限则可能因配置异常（如 max_tokens=100000）产生巨额请求。

### 3. `content` 为空时回退 `reasoning_content`

部分推理模型把正文放在 `reasoning_content`。回退并记 WARNING，避免把一次可用的输出判为失败。
仅在 `finish_reason != "length"` 时回退——截断场景下该字段同样不完整，走重试/失败路径。

### 4. `MIN_MAX_TOKENS = 4096` 安全下限加在 `LLMClient.__init__`

- **理由**：部署侧配置由 `merge_app_config.py` 保留，流水线改不动它。下限让「陈旧配置」这一现实问题
  自愈，而不是依赖运维记得手工同步。
- **代价**：配置值与实际生效值可能不一致（出现隐式覆盖）。用 WARNING 日志 + 「系统配置」页展示实际生效值
  来消解；这是一个有意为之的安全网，不是静默行为。
- **注意**：下限（4096）低于新默认值（16000）——下限只保证「不再发出空正文邮件」，不保证「一定不截断」。
  要让线上跑在 16000，仍需同步部署侧配置（见 Migration Plan）。

### 5. 引擎层加一次空内容纵深防御

`_call_llm` 除了捕获 `LLMError`，还校验返回值非空。理由：注入的 mock、未来新增的 client 实现、
或任何人绕过 `LLMClient` 时，引擎仍不会把空串当成功落库。这条防线正是本次故障的直接对应点。

### 6. 逐条失败 + 不引入新状态

`_call_llm` 失败时记 WARNING 并返回 `None`，调用方跳过该条目。运行状态：

```
failed_count and total_results == 0  → failed
否则                                  → succeeded（summary 标注失败数）
```

- **理由**：50 条里 1 条坏就整批失败（且已成功条目会因 `_log()` 的 commit 而留下）代价过高；
  而「全部失败」必须判失败，否则会推送一封空邮件。
- **备选**：新增 `partial` 状态。否决——需同步改前端、任务中心筛选、推送钩子判定，收益不抵成本。

### 7. 水位线只推进到成功条目的最大 `id`

- **收益**：失败集中在批次尾部时，其 `id` 大于水位线，下次 `sequential` 增量自动重跑。
- **残留局限**：失败条目若夹在中间（`id` 小于成功条目的最大 `id`），会被水位线越过而不再被 `sequential`
  增量选中，需用「全量」或「自定义」模式补跑。用 WARNING 记录条目 `id` + 摘要标注失败数来暴露。
- **备选**：本批有失败就不推进水位线。否决——会导致下次增量重复分析整批，产生重复结果与重复推送（更糟）。
- **备选**：新增「失败条目重试队列」。否决——超出本次范围，`newest_unanalyzed` 策略已天然覆盖重试场景。

### 8. 推送钩子改由局部标志位守卫

在 `try` 内于确定 `run.status = "succeeded"` 时置 `analysis_ok = True`，`else` 分支改为
`if analysis_ok: on_analysis_completed(task_id)`。不直接读 `run.status` 是为了避免 ORM 对象在 commit 后
的属性过期/脱离会话问题。

## Risks / Trade-offs

- [截断重试让单次分析成本最高翻倍] → 仅在实际发生截断时触发，且只重试一次；正常路径零额外开销。
- [安全下限造成「配置显示值与实际生效值不一致」] → WARNING 日志显式说明；`LLMClient` 把生效值存为
  `self.max_tokens`，系统配置页展示的是它，必要时可查。
- [失败条目夹在批次中间会被 `sequential` 增量永久越过] → 已在 WARNING（含条目 `id`）与运行摘要中暴露；
  文档与 `analysis-item-selection` 规格中写明需用「全量 / 自定义」补跑。
- [中途失败时 `_log()` 的 commit 会连带提交此前成功条目的结果与 `analyzed` 标记] → 这是既有行为，
  且方向正确（那些条目确实成功了）；本次不改动，避免引入事务边界重构。
- [回退 `reasoning_content` 可能把「思考过程」当作分析结果推送] → 仅在该字段非空且正文为空时触发，
  且记录 WARNING。相比「发一封空邮件」，这是更可接受的结果。

## Migration Plan

1. 合并代码并部署。代码内置下限即刻生效：部署侧残留的 `llm.max_tokens=2000` 会被抬到 4096，
   截断时还会自动重试到 8192——空正文邮件的直接诱因被消除。
2. **运维手工同步**（为了让线上真正跑在推荐值上）：把部署侧 `config/app.json` 的 `llm.max_tokens`
   改为 `16000`，或设置环境变量 `ISAS_LLM_MAX_TOKENS=16000` 后重启。流水线的增量合并不做这件事。
3. **回滚**：本次无数据库迁移、无接口变更，回滚即回退代码。回滚后若部署侧配置已被改为 16000，
   旧代码同样能正常读取（`max_tokens` 只是普通配置项），无兼容性风险。
4. **存量数据**：此前因空输出被误标为 `analyzed=True` 的条目不会被自动修复。若需重跑，
   可用「全量」模式或「自定义」模式选中这些条目重新分析。
