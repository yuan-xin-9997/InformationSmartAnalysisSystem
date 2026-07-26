# 设计规格：分析结果页改造 + 定时任务

- 日期：2026-07-25
- 范围：两项需求
  1. 删除独立的「分析结果」菜单页，改为从「分析任务」点「结果」下钻进入的任务结果详情页。
  2. 新增「定时任务」页面，可对分析任务配置定时调度（cron 表达式 + 简单间隔），到点自动触发分析。

## 1. 现状分析

### 1.1 分析结果（现状）

- 前端路由 `/analysis-result`（`router/index.ts:19`），组件 `views/AnalysisResult.vue`，侧边栏菜单项「分析结果」（`layouts/MainLayout.vue:61`），权限键 `analysis_result`（`core/pages.py:12`，grantable）。
- `AnalysisTasks.vue` 的「结果」按钮 `goResults(taskId)` -> `router.push('/analysis-result', query:{task_id})`（`AnalysisTasks.vue:282`）。
- `AnalysisResult.vue` 按 `task_id` 过滤，列表 + 点开 Modal 弹窗看 Markdown（`AnalysisResult.vue:29-37`）。
- 后端两个端点：
  - `GET /api/analysis-tasks/{task_id}/results`（`api/analysis_tasks.py:186`，权限 `analysis_tasks`）——按任务取结果，**保留**。
  - `GET /api/analysis-results`（`api/analysis_tasks.py:206`，权限 `analysis_result`）——全局结果列表，**删除**。

### 1.2 任务执行链路（定时任务复用基础）

- 手动触发：`POST /api/analysis-tasks/{id}/run` -> 创建 `TaskRun(kind="analysis", ref_id=task_id, ref_name, mode, status="pending")` -> `worker.submit(run_analysis, run.id, task_id, mode)`（`api/analysis_tasks.py:155-183`）。
- `worker.py`：进程级 `ThreadPoolExecutor`（max_workers 来自 `settings.worker_max_workers`），`submit(fn, *args)` 每作业独立线程 + 独立 DB 会话（`services/worker.py`）。
- `run_analysis(run_id, task_id, mode, llm_client=None)`（`services/analysis/engine.py:32`）：更新 TaskRun 状态、遍历 `task_sources`、调 LLM、写 `analysis_results`、推进水位线、写 `task_logs`。
- `main.py` lifespan：`setup_logging` -> `init_db` -> `sync_users` -> `yield` -> `worker.shutdown()`（`main.py:31-47`）。调度器在此启停。
- **无任何现成调度器/cron/apscheduler**，需新建。

### 1.3 权限机制（与权限键增删相关）

- `core/pages.py` 的 `PAGE_DEFINITIONS` 定义所有页面键；`GRANTABLE_PAGE_KEYS` 为可授予普通用户的键。
- `get_permissions` / `set_permissions`（`api/users.py:31-65`）已用 `GRANTABLE_PAGE_KEYS` 过滤：键从 `PAGE_DEFINITIONS` 移除后，`page_permissions` 表中残留记录会被自动忽略，下次 `set_permissions` 时被 delete 清除。**故删除 `analysis_result` 键无需专门数据迁移**；可选地在 `init_db` 顺手清理失效记录以保持表整洁。

## 2. 需求1：分析结果改为任务下钻详情页

### 2.1 删除项

- 侧边栏菜单项「分析结果」（`MainLayout.vue` 的 `allMenus` 与 `pageMeta`）。
- 路由 `/analysis-result`（`router/index.ts`）。
- 权限键 `analysis_result`（`core/pages.py` 的 `PAGE_DEFINITIONS`）。
- 旧组件 `views/AnalysisResult.vue`。
- 后端端点 `GET /api/analysis-results` 及其 `results_router`（`api/analysis_tasks.py:206-220`、`main.py:66` 的 `include_router(results_router)`）。
- 前端 `api/tasks.ts` 中仅服务于旧页的 `listAllResultsApi`（保留 `listTaskResultsApi`）。

### 2.2 新增项

- 路由 `/analysis-tasks/:id/results` -> 新组件 `views/TaskResults.vue`，**不在侧边栏**，仅由分析任务页「结果」按钮 `router.push({ name: 'task-results', params: { id } })` 进入。
- `meta: { page: 'analysis_tasks', title: '分析结果' }`——复用分析任务权限（能看任务即可看其结果），路由守卫逻辑不变；带参路由刷新由 SPA fallback 兜底（`main.py:85`）。

### 2.3 页面交互（TaskResults.vue）

- 顶部：当前任务名 + 任务切换下拉（`listTasksApi`）+ 刷新按钮。
- 按**运行批次（task_run）分组**：批次列表来自 `GET /api/task-center/runs?kind=analysis&ref_id={id}`（已有端点）。每个批次显示：运行时间、模式（全量/增量/自定义）、状态、摘要。
- 每批次下展开该批结果（`GET /api/analysis-tasks/{id}/results?run_id={run_id}`）：逐条/汇总标识、信息源名、创建时间。
- 点单条结果 -> **页内折叠面板展开 Markdown**（`utils/markdown.ts` 的 `renderMarkdown`），取代原弹窗。
- 空态：任务从未运行过分析时提示「暂无分析结果，触发分析后将在此展示」。

### 2.4 后端 API 调整

- 保留 `GET /api/analysis-tasks/{task_id}/results`（已支持 `run_id` 过滤，`api/analysis_tasks.py:186`）。
- 删除 `GET /api/analysis-results` 与 `results_router`。
- `task_center` 的 `GET /api/task-center/runs` 需支持 `kind` 与 `ref_id` 过滤（若已有则复用，否则补充）。

## 3. 需求2：定时任务

### 3.1 数据模型（新表 `scheduled_jobs`）

新增 `models/scheduled_job.py`，并在 `models/__init__.py` 注册以纳入 `Base.metadata`（建表）。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | 自增 |
| task_id | FK->analysis_tasks, CASCADE | 所属分析任务 |
| name | String(128) | 定时任务名 |
| mode | String(16) | `full` / `incremental` |
| trigger_type | String(16) | `cron` / `interval` |
| cron_expr | String(128), nullable | cron 模式填，如 `0 9 * * *` |
| interval_seconds | Integer, nullable | interval 模式填 |
| enabled | Boolean, default True | 启用状态 |
| last_run_at | DateTime, nullable | 最近触发时间（UTC） |
| last_run_status | String(16), nullable | 最近触发结果状态（succeeded/failed/...） |
| next_run_at | DateTime, nullable | 下次预计触发（北京时间展示） |
| created_at / updated_at | DateTime | |

- 无唯一约束（一个分析任务可配多条定时）。
- 删除分析任务时，`task_id` 级联删除其定时任务（CASCADE），并同步从调度器移除 job。

### 3.2 调度器实现（新建 `services/scheduler.py`）

- 使用 **APScheduler `BackgroundScheduler`**（方案 A，已批准）。
- 单例模块；时区取 `settings.timezone_display`（Asia/Shanghai），cron 表达式按北京时间解释（符合 CLAUDE.md 规范2）。
- `start_scheduler()`：lifespan 启动时调用；若 `settings.scheduler_enabled` 为 False 则跳过；否则从 DB 加载所有 `enabled=True` 的 job -> `add_job`。
  - trigger：`trigger_type=="cron"` 用 `CronTrigger.from_crontab(cron_expr, timezone=...)`；`"interval"` 用 `IntervalTrigger(seconds=interval_seconds, timezone=...)`。
  - `id=str(job.id)`、`func=_fire`、`args=[job.id]`、`max_instances=1`（防同 job 重叠，新触发被跳过）、`coalesce=True`（错过多 次只补一次）、`misfire_grace_time=settings.scheduler_misfire_grace_seconds`。
- `_fire(job_id)`：调度回调。
  1. 开 `SessionLocal`；查 `scheduled_job`；若不存在或已禁用则直接返回（防竞态）。
  2. 查关联 `AnalysisTask`（不存在则记日志返回）。
  3. 创建 `TaskRun(kind="analysis", ref_id=task_id, ref_name=task.name, mode=job.mode, status="pending")`，commit。
  4. `worker.submit(run_analysis, run.id, task_id, job.mode)`——**完全复用现有执行链路**。
  5. 更新 `scheduled_jobs.last_run_at`，`last_run_status` 先置 `"running"`；`next_run_at` 取调度器 `job.next_run_time`。
- **状态回写**：`run_analysis` 执行结束才知道成功/失败，且它在独立 worker 线程。为精确回写 `last_run_status`，给 `TaskRun` 增加可空列 `scheduled_job_id`（迁移友好，旧数据为 NULL），`_fire` 创建 run 时写入该 id；`run_analysis` 结束时若 `run.scheduled_job_id` 非空，则更新对应 `scheduled_job.last_run_status`（succeeded/failed）。手动触发的 run 该列为 NULL，不回写，不影响现有逻辑。
- `add_scheduled_job(job)` / `remove_scheduled_job(job_id)` / `reschedule_scheduled_job(job)`：CRUD 时同步调度器内存 job，保持 DB 与调度器一致。
- `shutdown_scheduler()`：lifespan 关闭时调用（`worker.shutdown()` 之前）。
- 并发与线程安全：APScheduler 内部线程触发 `_fire`；`_fire` 用独立 DB 会话，与 worker 一致。

### 3.3 API（新建 `api/scheduled_jobs.py`，前缀 `/api/scheduled-jobs`）

所有端点 `require_page("scheduled_jobs")`。

| 端点 | 功能 |
|---|---|
| `GET ""` | 列表，支持 `task_id`、`enabled` 过滤；返回 `next_run_at`（北京时间）等 |
| `POST ""` | 创建：校验 task 存在、`mode` 合法、trigger 合法、`cron_expr` 能被 `CronTrigger.from_crontab` 解析（非法返回 400 中文提示）；写 DB -> `add_scheduled_job` -> 回填 `next_run_at` |
| `PUT /{id}` | 更新：同样校验；写 DB -> `reschedule_scheduled_job` |
| `DELETE /{id}` | 删除：`remove_scheduled_job` -> 删 DB |
| `POST /{id}/toggle` | 启用/禁用切换：写 DB -> 启用则 `add_scheduled_job`，禁用则 `remove_scheduled_job` |
| `POST /{id}/run` | 立即执行一次：创建 `TaskRun`（`scheduled_job_id` 写入）+ `worker.submit(run_analysis, ...)`；不影响 `next_run_at`；返回 `run_id` |

- Pydantic schemas 放 `schemas/scheduled_job.py`。
- 时间字段出参转北京时间（复用现有 `timeutil` 转换约定）。

### 3.4 前端页面

- 新菜单「定时任务」（`MainLayout.vue` `allMenus` + `pageMeta`），路由 `/scheduled-jobs`，`meta.page='scheduled_jobs'`，`router/index.ts` 增路由，`pages.py` 增键（grantable=True）。
- 新组件 `views/ScheduledJobs.vue`：
  - 列表列：名称、所属任务、模式、调度摘要（如「每天 09:00」/「每 30 分钟」）、启用状态、下次执行、上次执行/状态、操作（编辑/启停/立即执行/删除）。
  - 新建/编辑弹窗：所属任务（下拉，`listTasksApi`）、名称、模式（增量/全量）、触发类型（cron/间隔）、cron 表达式（带常用预设：每天9点 `0 9 * * *`、工作日9点 `0 9 * * 1-5`、每小时 `0 * * * *`、每30分钟 `*/30 * * * *`）或间隔秒数、启用开关。
  - 前端对 cron 做基本格式校验，严格校验由后端 `CronTrigger.from_crontab` 完成。
- 新增 `api/scheduledJobs.ts` 封装上述端点。
- `AnalysisTasks.vue` 任务卡片可选增强：显示「已配 N 个定时」（`GET /api/scheduled-jobs?task_id=` 取数）。

### 3.5 执行历史

- 定时触发的执行记录即 `TaskRun(kind="analysis")`，**复用「任务中心」**展示（已支持运行列表/状态/日志）。
- 定时任务页只显示「下次执行 / 上次执行摘要 / 立即执行」；不单独做历史列表。

## 4. 横切调整

### 4.1 权限与菜单

- `core/pages.py`：删除 `analysis_result`；新增 `scheduled_jobs`（grantable=True）。
- `MainLayout.vue`：删除「分析结果」菜单项；新增「定时任务」菜单项。
- `router/index.ts`：删 `/analysis-result`；增 `/analysis-tasks/:id/results` 与 `/scheduled-jobs`。
- 普通用户的 `scheduled_jobs` 授权由管理员在「权限管理」页配置（独立可授权页，已批准）。

### 4.2 配置（`config/app.json` + `core/config.py`）

`app.json` 新增：
```json
"scheduler": {
  "enabled": true,
  "misfire_grace_seconds": 300,
  "max_instances": 1,
  "coalesce": true
}
```
`core/config.py` 的 `Settings` 增加对应字段，支持 `ISAS_SCHEDULER_ENABLED` / `ISAS_SCHEDULER_MISFIRE_GRACE_SECONDS` 等环境变量覆盖（符合规范1：不硬编码）。

### 4.3 依赖

- `requirements.txt` 增加 `apscheduler>=3.10`。
- 前端无新增依赖。

### 4.4 数据库迁移

- 新表 `scheduled_jobs`、`task_runs` 新增可空列 `scheduled_job_id`：由 SQLAlchemy `Base.metadata.create_all` 在 `init_db` 自动建表/加列（现有项目用 `create_all`，新表新列自动处理；旧 `task_runs` 行的 `scheduled_job_id` 为 NULL，不影响现有逻辑）。

## 5. 测试策略（pytest，全部须通过）

### 5.1 单元测试

- `scheduled_jobs` 模型字段与级联（删任务 -> 删其定时）。
- cron/interval 触发器构建（合法/非法 cron 表达式 -> 400）。
- `_fire`：创建 `TaskRun`（含 `scheduled_job_id`）并 `worker.submit`（mock `run_analysis`/LLM）；已禁用 job 不触发。
- CRUD 同步调度器：`add_scheduled_job`/`remove_scheduled_job`/`reschedule_scheduled_job` 用 mock scheduler 断言调用。
- 调度器启停：`scheduler_enabled=False` 时不启动。
- `run_analysis` 完成后回写 `scheduled_job.last_run_status`（mock LLM，成功/失败两路）。
- 权限：无 `scheduled_jobs` 权限的普通用户访问端点 -> 403。
- 删除 `analysis_result` 键后，旧 `page_permissions` 残留不影响 `get_permissions`。

### 5.2 冒烟测试

- 登录 -> 建信息源 -> 建分析任务绑定源 -> 建定时任务（interval 短间隔或用「立即执行」）-> 触发 -> 任务中心见 run succeeded -> 结果详情页见结果。
- 启用/禁用/编辑/删除定时任务全流程。
- 分析任务页点「结果」-> 进入任务结果详情页，按批次分组展示。
- 所有外部依赖（LLM/WebFetch）mock，不依赖真实网络。

## 6. 受影响文件清单

### 后端
- 新增：`models/scheduled_job.py`、`schemas/scheduled_job.py`、`api/scheduled_jobs.py`、`services/scheduler.py`
- 修改：`models/__init__.py`（注册新模型）、`models/task.py`（`TaskRun` 加 `scheduled_job_id`）、`main.py`（lifespan 启停调度器、挂载新路由、移除 `results_router`）、`api/analysis_tasks.py`（删 `results_router`/`list_results`）、`api/task_center.py`（确认/补充 `kind`+`ref_id` 过滤）、`core/pages.py`、`core/config.py`、`config/app.json`、`requirements.txt`、`config/env.local.example`（补 scheduler 示例）

### 前端
- 新增：`views/TaskResults.vue`、`views/ScheduledJobs.vue`、`api/scheduledJobs.ts`
- 修改：`router/index.ts`、`layouts/MainLayout.vue`、`views/AnalysisTasks.vue`（`goResults` 改跳新路由；可选「已配 N 个定时」）、`api/tasks.ts`（删 `listAllResultsApi`、`AnalysisResult` 类型按需调整）
- 删除：`views/AnalysisResult.vue`

### 文档
- 更新：`README.md`、`docs/需求规格说明书.md`、`docs/设计说明书.md`（页面/接口/表结构/权限键变更）

## 7. 规范遵循

- 规范1（不硬编码）：调度器参数全部走 `config/app.json` + `ISAS_*` 环境变量；cron/间隔由用户填，非硬编码。
- 规范2（北京时间）：调度器时区用 `settings.timezone_display`；`next_run_at` 等出参转北京时间展示；存储 UTC。
- 规范3（下载文件按年月日）：本次无新增下载，不涉及。
- 基础模块：定时任务页作为新增功能页，纳入权限管理体系（独立可授权键）。
- 部署：无新增部署脚本改动；`requirements.txt` 新增 `apscheduler`，`start.sh` 装依赖时自动安装。

## 8. 风险与边界

- **APScheduler 与 uvicorn 多 worker**：本项目 uvicorn 单 worker + 进程内 ThreadPoolExecutor，APScheduler `BackgroundScheduler` 进程内运行，无多实例冲突。若未来改为多 worker 部署，需改用持久化 jobstore + 分布式锁（本次不涉及，记录为已知约束）。
- **调度器重启恢复**：调度器状态不持久化（不依赖 APScheduler jobstore），重启时从 DB 重建 job；`enabled=False` 的不加载。
- **`_fire` 竞态**：job 在调度器内存中存在但 DB 已被禁用/删除时，`_fire` 再次查 DB 校验，已禁用/不存在则跳过。
- **立即执行与调度重叠**：`max_instances=1` 仅约束同一调度 job；「立即执行」走独立 `TaskRun`，不与调度 job 的 `max_instances` 冲突（二者均为独立 run，由 worker 线程池并发上限兜底）。
