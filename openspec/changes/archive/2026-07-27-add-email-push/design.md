## Context

本系统是一个信息智能分析系统：信息源（`InfoSource`）抓取信息条目（`InfoItem`），分析任务（`AnalysisTask`）绑定信息源并经 LLM 产出分析结果（`AnalysisResult`，`result_type` 取值 `per_item`/`aggregate`）；定时任务（`ScheduledJob`）按 cron/间隔自动触发分析；`TaskRun`/`TaskLog` 记录每次执行。所有配置读自 `config/app.json`（`core/config.py` 的 `Settings`，支持 `ISAS_*` 环境变量覆盖），系统配置页只读展示（敏感字段脱敏）。后台执行统一走 `services/worker.py` 的进程级 `ThreadPoolExecutor`（每任务独立线程 + 独立 DB 会话）；定时调度走 `services/scheduler.py` 的进程级 APScheduler `BackgroundScheduler`（`MemoryJobStore`，启动时从 DB 加载已启用任务，CRUD 实时同步）。数据库为 SQLite，建表靠 `init_db()` 的 `Base.metadata.create_all` + `_ensure_column` 轻量迁移。页面权限由 `core/pages.py` 的 `PAGE_DEFINITIONS` 驱动，前后端共用。

本次新增「邮件推送」：把增量分析结果（事件）按管理员配置的推送规则，在三种触发时机推送到邮箱。推送对象经确认为 `AnalysisResult`；触发方式为「任务完成后自动 / 按计划定时 / 手动」三选一（每条规则由用户选择）；订阅全局管理员配置；SMTP 配置页面优先于 `app.json`。

## Goals / Non-Goals

**Goals:**
- 管理员可在「推送管理」页配置推送规则（选定任务、事件类型、收件人、触发方式），并管理 SMTP 配置。
- 按 `AnalysisResult.id` 水位线实现增量推送，三种触发方式统一复用同一推送执行路径。
- SMTP 配置页面优先、`app.json` 回退，两处皆无时明确报错；敏感字段脱敏。
- 推送渠道结构可扩展（当前实现邮件），推送规则与触发逻辑不因渠道增加而改动。
- 推送执行全程留痕（推送历史），失败不推进水位线以支持重试。
- 复用现有 worker / scheduler / 权限 / 配置机制，不引入第三方依赖（邮件用标准库 `smtplib`+`email`）。

**Non-Goals:**
- 不实现邮件以外的推送渠道（webhook、IM 等），仅留好扩展点。
- 不做按用户维度的个性化订阅（订阅为全局管理员配置）。
- 不做推送规则的版本管理 / 审批流。
- 不重写现有分析引擎，仅在分析成功后增加一个推送钩子。
- 不引入消息队列或独立推送进程（复用进程内 worker + scheduler 即可）。

## Decisions

### 决策 1：数据模型 — 三张新表

新增三张表，均由 `init_db()` 的 `create_all` 自动建表：

- `push_rules`：`id`、`name`、`channel`(默认`"email"`)、`task_ids`(JSON 数组)、`event_types`(JSON 数组，取值 `per_item`/`aggregate`)、`recipients`(JSON 数组邮箱)、`trigger_mode`(`on_run`/`scheduled`/`manual`)、`cron_expr`、`interval_seconds`、`enabled`(默认 true)、`last_pushed_result_id`(水位线，可空)、`max_events_per_email`(默认 50)、`created_at`、`updated_at`。
- `push_runs`（推送历史）：`id`、`rule_id`(FK `push_rules` CASCADE)、`trigger_mode`、`recipients`(快照 JSON)、`event_count`、`status`(`succeeded`/`failed`/`no_new`)、`error`(Text)、`started_at`、`finished_at`、`created_at`。
- `smtp_config`（单行配置表，`id=1` 固定）：`host`、`port`、`use_tls`、`use_ssl`、`username`、`password`、`from_email`、`from_name`、`reply_to`。

**为什么用 JSON 数组存 `task_ids`/`event_types`/`recipients`**：与现有 `AnalysisTask.config` 一致地使用 JSON 列，避免引入联表带来的迁移与级联复杂度；任务被删除时按「跳过缺失」处理即可。**为什么单行 `smtp_config`**：SMTP 配置是全局单例，单行表最简单；`id=1` 约定，保存时 upsert 该行。**为什么水位线是单值而非按任务分值**：`AnalysisResult.id` 是全局单调递增主键，单条规则用 `id > last_pushed_result_id` 即可正确选出跨任务的增量，无需按任务分别记水位。

*备选*：`push_rule_tasks` 联表 + 按任务水位线表。更规范但增加 2 张表与级联逻辑，收益有限，放弃。

### 决策 2：SMTP 配置分层解析器

新增 `services/push/smtp_config.py` 的 `resolve_smtp_config()`：先读 `smtp_config` 表（`id=1`）；若该行存在且含 `host`+`from_email` 等最小必需项，则采用（密码字段为空时允许，按服务器要求）；否则回退到 `Settings` 中新增的 `email` 段（`app.json`）；两处都缺最小必需项时抛出带明确信息的异常。读取接口返回时复用 `core/secrets.py` 的脱敏逻辑对 `password` 脱敏。

`core/config.py` 新增 `email` 段解析（`email_smtp_host`/`email_smtp_port`/`email_use_tls`/`email_username`/`email_password`/`email_from_email`/`email_from_name`，均带 `ISAS_EMAIL_*` 环境变量覆盖），`config/app.json` 增加对应默认段（值留空，由部署方填写）。

**为什么页面优先**：用户明确要求；页面配置可热更新无需改文件重启。**为什么仍保留 `app.json` 段**：首次部署 / 无页面配置时的兜底，且便于 systemd/容器化场景用环境变量注入。

### 决策 3：推送执行统一走 worker

新增 `services/push/service.py` 的 `run_push(rule_id, trigger_mode)`，在 worker 线程中独立 DB 会话执行：
1. 载入规则，禁用则直接返回；
2. `resolve_smtp_config()`，缺失则写 `push_runs(failed)` 并返回；
3. 查询 `AnalysisResult`：`task_id IN rule.task_ids AND result_type IN rule.event_types AND id > rule.last_pushed_result_id`（水位线为空则不含该条件），`order_by id asc`；
4. 为空 → 写 `push_runs(no_new)` 返回；
5. 按 `max_events_per_email` 分批：每批渲染一封邮件（HTML 正文 + 纯文本备用，时间用 `core/timeutil` 转北京时间），经渠道发送；
6. 每批发送成功后立即把 `last_pushed_result_id` 推进到本批最大 id 并提交；
7. 任一批失败 → 写 `push_runs(failed, error)`，**不推进**该批水位线，剩余批不再发送（下次推送从该批重试）；
8. 全部成功 → 写 `push_runs(succeeded, event_count=总数)`。

**为什么分批发送**：避免单封邮件过大被 SMTP 拒绝或客户端卡死；并以批为单位推进水位线，使部分失败时已发送的批不会重发。**为什么失败不推进水位线**：保证「至少送达一次」语义，下次自动重试。**为什么用 worker**：SMTP 发送耗时不可控，不能阻塞 API/分析线程；与现有 `run_analysis` 一致。

*备选*：同步在请求线程发送（手动触发场景）。手动触发也走 worker，前端提交后刷新历史即可，避免长请求超时；仅「发送测试邮件」走同步以即时返回结果。

### 决策 4：触发集成

- **on_run**：在 `services/analysis/engine.py` 中，`run.status="succeeded"` 提交成功后，调用 `push_service.on_analysis_completed(task_id)`（新建，避免 engine 直接依赖规则模型细节）。该函数查询 `enabled=true AND trigger_mode='on_run' AND task_ids 含 task_id` 的规则，对每条 `worker.submit(run_push, rule.id, "on_run")`。分析失败分支不调用。水位线幂等性保证并发完成不会重复推送（第二条推送查到无新事件即 `no_new`）。
- **scheduled**：复用 `scheduler.py` 的同一个 `BackgroundScheduler`。将 `scheduler.py` 的私有 `_scheduler` 抽出 `get_scheduler()` 访问器（或新增 `register_external_job` 入口），新增 `services/push/push_scheduler.py`：用命名空间 job id `push-{rule_id}` 注册 `scheduled` 规则，回调 `worker.submit(run_push, rule_id, "scheduled")`；CRUD 时 `add/remove/reschedule`，启动时在 `main.py` lifespan 调 `start_push_scheduler()` 加载已启用规则。`max_instances=1`、`coalesce=True` 复用 `settings.scheduler_*`。
- **manual**：`POST /api/push-rules/{id}/trigger` → `worker.submit(run_push, id, "manual")`，返回 202 + 提示，前端刷新历史查看结果。

**为什么复用同一个 BackgroundScheduler**：避免第二个调度线程，统一时区与 misfire 配置；APScheduler 支持多 job 共存，job id 命名空间隔离即可。**为什么 on_run 用钩子而非事件总线**：系统无事件总线，引入会过度设计；一个直接函数调用足够，且把规则查询封装在 push_service 内，engine 只需一行调用。

*备选*：新建独立 `BackgroundScheduler` 给推送。多一个线程与配置项，无额外收益，放弃。

### 决策 5：可扩展渠道抽象

`PushRule.channel` 字段（默认 `"email"`）。新增 `services/push/channels/base.py` 定义 `PushChannel` 协议（`send(ctx, recipients, subject, html, text) -> None`）与 `EmailChannel` 实现（标准库 `smtplib.SMTP`/`SMTP_SSL` + `email.mime`）。`services/push/channels/__init__.py` 维护 `CHANNELS = {"email": EmailChannel}` 注册表。`run_push` 按 `rule.channel` 取实现。新增渠道只需加一个类并注册，规则与触发逻辑不动。

**为什么现在就抽象**：用户明确「目前是邮件推送」暗示后续有其他渠道；现在用 protocol + 注册表成本极低，避免日后改 `run_push` 主体。

### 决策 6：邮件内容与主题

- 主题：`【信息分析】{rule_name} - {n}条新事件`。
- HTML 正文：表格/列表逐条列出 `任务名`、`类型`（`per_item`→「逐条分析」、`aggregate`→「汇总分析」）、`来源`、`时间`（北京时间）、`内容`（LLM 输出原样置于 `<pre>` 或基本转义，不做 markdown 渲染，避免引入渲染依赖）。
- 纯文本备用正文：同内容去标签。
- 编码：UTF-8（`email` 标准库默认支持中文）。

### 决策 7：权限与页面

`core/pages.py` 的 `PAGE_DEFINITIONS` 增加 `{"key":"push_management","label":"推送管理","grantable":true}`（与 `analysis_tasks` 等一致，管理员可在权限管理页授予）。前端 `router` 增加 `/push-management` 路由 + 菜单项，`meta.page="push_management"`，复用现有路由守卫。所有推送相关 API 用 `Depends(require_page("push_management"))`。

## Risks / Trade-offs

- [首次推送可能量大] 水位线为空时推送全部历史匹配事件 → 由 `max_events_per_email` 分批缓解；管理员知晓后可接受一次性补推。*Trade-off*：不引入「是否包含历史」开关，保持规则语义简单可预测。
- [SMTP 凭据泄露] `smtp_config.password` 明文存 SQLite → 读取接口脱敏；数据库文件本身按部署规范保护（与现有 `llm.api_key` 同级别风险与处置）。*Trade-off*：不做应用层加密，避免密钥管理复杂度，与现有敏感配置处置一致。
- [推送与分析争抢 worker 线程] 两者共用 `ThreadPoolExecutor`（默认 4 线程）→ 推送任务通常短，影响可控；如需隔离可调大 `worker.max_workers`。*Mitigation*：分批发送使单任务耗时可控。
- [on_run 钩子失败影响分析] engine 调用 push 钩子若抛异常不应影响已成功的分析 → 钩子内部 try/except 吞异常并记日志，仅记 `push_runs(failed)`，不向 engine 传播。
- [调度器实例共享的耦合] push_scheduler 依赖 scheduler.py 暴露调度器 → 通过稳定访问器 `get_scheduler()` 解耦，命名空间 job id 隔离；若 scheduler 被禁用（`scheduler.enabled=false`），定时推送也随之不可用（合理：无调度器则无定时能力），on_run 与手动不受影响。
- [收件人邮箱错误 / 退信] SMTP 可能因无效邮箱返回错误 → 记入 `push_runs.error`，不推进水位线导致反复重试同一无效地址。*Mitigation*：对「收件人被服务器拒绝」类错误，仍标记 failed 但在设计中作为开放问题（见下），v1 接受重试。

## Migration Plan

1. 后端：新增 `models/push.py`（三张表模型）；`services/push/` 包（`service.py`/`smtp_config.py`/`channels/`/`push_scheduler.py`）；`api/push.py`；`core/config.py` 加 `email` 段；`core/pages.py` 加 `push_management`；`main.py` 注册路由并在 lifespan 启动 `start_push_scheduler()`；`engine.py` 加 on_run 钩子调用。
2. 前端：新增 `views/PushManagement.vue`、`api/push.ts`、路由与菜单项。
3. 配置：`config/app.json` 增加 `email` 段（值留空）。
4. 部署：`init_db()` 自动建新表，无需手工迁移；首次部署后管理员在页面配置 SMTP 与规则。增量部署仅需重启服务（lifespan 加载新调度）。
5. 回滚：移除推送路由注册与 lifespan 中的 `start_push_scheduler()`、engine 钩子调用；新表保留无副作用（可后续清理）。回滚后 `app.json` 的 `email` 段被忽略。

## Open Questions

- 收件人被 SMTP 服务器永久拒绝（无效地址）时，是否需要「失败但推进水位线」以免无限重试？v1 暂按「失败不推进」统一处理，待真实退信反馈后再细化错误分类。
- 邮件正文是否需要把 LLM 输出按 markdown 渲染？v1 用 `<pre>` 原样展示，避免引入渲染依赖；如体验不佳再考虑轻量渲染。
- 是否需要推送规则的「静默时段」（如夜间不发）？v1 不做，由 cron 表达式自行控制时段。
