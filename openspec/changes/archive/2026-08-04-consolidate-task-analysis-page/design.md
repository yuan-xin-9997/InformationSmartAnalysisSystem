## Context

当前系统围绕「分析任务」有三块独立能力，分散在三个前端页面与对应后端模型/接口：

- **分析任务**（`views/AnalysisTasks.vue` + `api/analysis_tasks.py` + `models/analysis.py`）：`AnalysisTask`（名称、说明、JSON `config`、绑定 `TaskSource`）。`config.mode` ∈ `per_item|aggregate|custom`，`config.selection_strategy` ∈ `sequential|newest_unanalyzed`。
- **定时任务**（`views/ScheduledJobs.vue` + `api/scheduled_jobs.py` + `models/scheduled_job.py`）：`ScheduledJob`，外键 `task_id` 指向 `analysis_tasks`，字段 `mode(full|incremental)`、`trigger_type(cron|interval)`、`cron_expr`、`interval_seconds`、`enabled`、`last_run_*`、`next_run_at`。**无 `task_id` 唯一约束**--一任务可有多条定时（N:1）。
- **推送管理**（`views/PushManagement.vue` + `api/push.py` + `models/push.py` + `services/push/*`）：`PushRule` 用 `task_ids: list`（JSON 数组）关联**多个**任务（N:M），字段 `event_types`、`recipients`、`trigger_mode(on_run|scheduled|manual)`、`cron_expr`/`interval_seconds`、`enabled`、`last_pushed_result_id`（全局水位线，`AnalysisResult.id` 全局单调）、`max_events_per_email`。`PushRun` 记录历史，`SmtpConfig` 单例（`id=1`，页面优先于 `app.json`）。

权限与路由：`core/pages.py` 的 `PAGE_DEFINITIONS` 含 `analysis_tasks`/`scheduled_jobs`/`push_management` 三个可授权键；`router/index.ts` 有 `/analysis-tasks`、`/scheduled-jobs`、`/push-management` 三条路由；`MainLayout.vue` 侧边栏三入口。

数据库迁移机制（`core/database.py`）：无 Alembic；`init_db()` 在启动时跑 `Base.metadata.create_all`（只建新表，不改旧表）+ `_ensure_column`（对旧表 `ALTER TABLE ADD COLUMN`）。SQLite 限制：不能 `ALTER TABLE` 加/改约束，但**可以** `CREATE UNIQUE INDEX IF NOT EXISTS`（需先去重）；不能轻易 `DROP COLUMN`（旧版本）。`event-push` 现有规格要求推送规则在「推送管理」页集中管理且可多选任务--本次变更这两点。

约束（CLAUDE.md）：不硬编码环境信息；时间显示北京时间；优先 SQLite/Python/FastAPI+Vue；无新依赖（前端仍为 Vue3 + 原生 HTML/CSS，无 UI 库）。

## Goals / Non-Goals

**Goals:**
- 三页合一为「任务分析」，任务编辑弹窗分区一体化配置「基本信息 + 定时分析 + 推送配置」，一次保存。
- 定时任务、推送配置收敛为每任务 1:1，归属关系在任务列表摘要一目了然。
- 平滑迁移已有数据：多任务推送规则按任务拆分、多余定时收敛、用户权限迁移，且迁移幂等、可在启动时自动执行。
- 移除冗余页面/路由/权限键，旧路由重定向，不破坏推送/调度的核心语义（水位线、三种触发、SMTP 分层、历史）。

**Non-Goals:**
- 不改动分析引擎本身（`services/analysis/*` 的 LLM 调用、结果生成逻辑）。
- 不改动信息源管理、任务中心、分析结果页、权限管理页（除页面键清单与显示名外）。
- 不新增推送渠道（仍仅邮件）；不改动邮件渲染与 SMTP 发送实现。
- 不引入前端 UI 库或 Alembic；不重构 `task_runs`/`AnalysisResult` 结构。
- 不保留独立的「定时任务」「推送管理」页（明确移除，非隐藏）。

## Decisions

### 决策 1：定时任务收敛为 1:1--保留 `ScheduledJob` 表，加 `task_id` 唯一索引
保留 `ScheduledJob` 独立表（调度器 `services/scheduler.py` 继续以 `ScheduledJob` 行为单元），不把调度字段嵌入 `AnalysisTask`。迁移去重后，用 `CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_jobs_task_id ON scheduled_jobs(task_id)` 在 DB 层强制每任务至多一条。服务层保存时用 upsert 语义（按 `task_id` 存在则更新、不存在则新建）。
**理由**：保留表让调度器/`task_runs.scheduled_job_id` 外键不动；唯一索引比重建表轻量；upsert 在服务层兜底避免并发写冲突。
**备选**：把调度字段嵌入 `AnalysisTask`--被否（要迁移 `task_runs.scheduled_job_id` 外键、改调度器读取逻辑， churn 大）。保留 N:1 仅 UI 取首条--被否（数据仍有歧义、约束缺失）。

### 决策 2：推送配置由多任务 N:M 改为单任务 1:1--`PushRule` 加 `task_id` 外键+唯一索引，弃用 `task_ids`
`PushRule` 新增 `task_id`（外键 `analysis_tasks.id`，唯一索引），移除模型对 `task_ids` 的使用。推送服务筛选由 `AnalysisResult.task_id IN (rule.task_ids)` 改为 `== rule.task_id`。`last_pushed_result_id` 水位线语义不变（现已是每规则一条，1:1 后即每任务一条）。DB 旧列 `task_ids` 暂留为孤儿列（被代码忽略），避免 SQLite `DROP COLUMN` 风险，后续可清理。
**理由**：1:1 与「编辑里配置推送」诉求一致，归属清晰；`AnalysisResult.id` 全局单调保证水位线在拆分后仍正确（见决策 6）；唯一索引防重复。
**备选**：保留 `task_ids` 仅在 UI 限制单选--被否（模型仍允许多任务，约束缺失，非真正 1:1）。嵌入 `AnalysisTask`--被否（推送服务/历史/SMTP 耦合大）。

### 决策 3：任务编辑弹窗用 Tab 分区--「基本信息 / 定时分析 / 推送配置」
弹窗改为 3 个 Tab，每个 Tab 标题旁带状态徽标（如「定时：已配置」「推送：未配置」），让用户在 Tab 切换前即知配置状态。保存按钮在弹窗底部统一提交三个区。基本信息 Tab 保留现有全部字段与「选择条目」弹窗（`item-selection-modal` 能力不动）。定时分析 Tab：启用开关 + 模式 + 触发类型 + cron/间隔 + 快捷预设 + 立即执行。推送配置 Tab：启用开关 + 事件类型 + 收件人 + 触发方式 + 定时参数 + 每封最大事件数 + 立即推送 + 推送历史入口。
**理由**：Tab 比单页长表单更清晰；徽标复用任务列表摘要的状态计算，避免「忘了配置某区」。
**备选**：单页堆叠 fieldset--被否（表单过长，定时/推送字段较多）。手风琴--被否（原生实现复杂度高于 Tab）。

### 决策 4：API 改为任务维度的一体化端点（1:1 upsert），移除旧独立端点
新增任务维度端点（1:1 upsert 语义）：
- `GET /api/analysis-tasks` 列表每项附带 `schedule` 与 `push` 摘要（启用状态、调度描述、收件人数、触发方式）。
- `GET /api/analysis-tasks/{id}` 详情附带 `schedule` 与 `push` 完整配置。
- `PUT /api/analysis-tasks/{id}` 保存时 body 可含 `schedule` 与 `push`，后端 upsert（存在则更新、不存在则新建；传 `null` 表示删除该子配置）。一次事务提交，避免部分成功。
- `POST /api/analysis-tasks/{id}/schedule/run`（立即执行定时分析）、`POST /api/analysis-tasks/{id}/push/trigger`（手动推送）、`GET /api/analysis-tasks/{id}/push/runs`（按任务推送历史）。
- `/api/push/smtp`（全局 SMTP，GET/PUT/测试）保留不动。
移除 `/api/scheduled-jobs/*` 与 `/api/push/rules/*`（页面已无入口，且 1:1 后语义改变）。
**理由**：任务维度端点与 1:1 模型一致，前端一次保存一个事务；移除旧端点避免双套 API 维护负担（个人系统无外部调用方）。
**备选**：保留旧端点 + 前端编排三次调用--被否（部分失败风险、双套 API）。仅前端编排不新增统一端点--被否（无原子性）。

### 决策 5：SMTP 配置作为「任务分析」页底部全局折叠区
原「推送管理」页的 SMTP 配置区迁移为「任务分析」页底部的全局「邮件通道（SMTP）」折叠区（默认折叠），单例语义与「页面优先于 app.json」不变。`/api/push/smtp` 接口与 `SmtpConfig` 模型不动。
**理由**：SMTP 是推送的依赖且为全局配置，与任务同页可发现性最好；折叠避免挤占任务列表视线。
**备选**：迁到「系统配置」页--被否（系统配置页定位是只读展示运行配置，SMTP 需可编辑+测试，职责不符）。

### 决策 6：多任务推送规则拆分--每任务一条，水位线原样复制
迁移时对每条 `PushRule`（含 N 个 `task_ids`）：为每个 `task_id` 生成一条新 `PushRule`，复制 `event_types`/`recipients`/`trigger_mode`/`cron_expr`/`interval_seconds`/`enabled`/`max_events_per_email`，`task_id` 设为该任务，`last_pushed_result_id` **原样复制**原规则的水位线。原多任务规则删除。
**理由**：`AnalysisResult.id` 全局单调，原水位线 W 表示「id ≤ W 的结果（跨所有任务）已推送过」；拆分后每条新规则以 W 为水位线，只会推送该任务 `id > W` 的结果，不会重推、不会漏推。
**备选**：按任务重算水位线为「该任务已推送结果的最大 id」--被否（需逐任务扫描 `PushRun`/`AnalysisResult`，复杂且原规则未按任务记录推送明细，原样复制更简单且正确）。

### 决策 7：权限与路由收敛--保留键 `analysis_tasks` 改显示名，移除两键，旧路由重定向
`core/pages.py`：移除 `scheduled_jobs`、`push_management` 两条；`analysis_tasks` 的 `label` 改为「任务分析」。`router/index.ts`：`/analysis-tasks` 路由 meta.title 改「任务分析」并作为唯一页；`/scheduled-jobs`、`/push-management` 改为重定向到 `/analysis-tasks`。`MainLayout.vue` 侧边栏移除两入口，「分析任务」改「任务分析」。权限迁移见决策 8。
**理由**：保留 `analysis_tasks` 键避免改权限模型主键；旧路由重定向保证书签/旧链接不 404。
**备选**：把键也改为 `task_analysis`--被否（要改权限存储与鉴权判定，churn 大、收益低）。

### 决策 8：迁移在 `init_db()` 中幂等执行（数据先于约束）
在 `init_db()` 的 `create_all` 之后追加一个 `_migrate_consolidate_task_analysis(engine)` 函数，幂等：
1. `_ensure_column(engine, "push_rules", "task_id", "INTEGER")`。
2. **数据迁移**（仅对未迁移数据，用「`task_id` 为空且 `task_ids` 非空」判定旧规则）：拆分多任务规则（决策 6）；对单任务规则回填 `task_id`；`scheduled_jobs` 按 `task_id` 保留最新一条、删多余；用户权限：凡 `pages` 含 `scheduled_jobs`/`push_management` 者，补 `analysis_tasks`、移除两旧键（用户权限存于 `users` 表 JSON）。
3. **去重后加唯一索引**：`CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_jobs_task_id ...`、`uq_push_rules_task_id ...`（去重保证创建成功）。
迁移函数用「检测哨兵」（如 `push_rules` 是否还存在 `task_ids` 非空且 `task_id` 为空的行）保证幂等，已迁移则跳过。
**理由**：沿用项目既有轻量迁移模式（无 Alembic）；数据先于约束保证索引创建成功；幂等保证重复启动安全。
**备选**：手写一次性脚本--被否（需人工执行、易忘）；引入 Alembic--被否（过度工程，项目无此先例）。

## Risks / Trade-offs

- **[BREAKING] 失去「一条推送规则管多任务」能力** -> 等价效果可由「多任务配置相同收件人」达成；迁移已按任务拆分，存量配置不丢失。已在 proposal 标注 BREAKING。
- **[迁移风险] 多任务规则拆分后收件人收到多封邮件** -> 拆分后若原一条规则覆盖 N 个任务且都产生新结果，原本一封邮件汇总，拆分后每个任务独立推送可能变多封。缓解：迁移文档提示用户复核；后续可按需合并收件人。属可接受行为变化（1:1 模型的固有结果）。
- **[迁移风险] 唯一索引创建失败（残留重复 `task_id`）** -> 迁移函数先去重再建索引；若失败则抛错并在日志明示，启动中断以便人工介入（优于静默放行）。
- **[SQLite] `task_ids` 孤儿列残留** -> 代码不再读写，仅占少量空间；记录于设计文档，后续可选清理。
- **[部分保存] 一体化保存的事务边界** -> `PUT /api/analysis-tasks/{id}` 在单事务内 upsert 任务/调度/推送；任一失败整体回滚，前端提示错误并重载，避免半成品状态。
- **[并发] 同一任务调度与推送并发触发** -> 现有调度器/推送服务已有处理，本次不改其并发语义，风险不变。

## Migration Plan

部署步骤（增量部署，`data/app.sqlite3` 已存在）：
1. 拉取新代码，重启服务；`init_db()` 自动执行 `_migrate_consolidate_task_analysis`（幂等）。
2. 启动日志确认：「拆分 N 条多任务推送规则」「收敛 M 个多余定时」「迁移 K 个用户权限」「创建 2 个唯一索引」。
3. 回滚策略：迁移不可逆（旧 `task_ids` 多任务语义已拆分）。回滚需从此前 SQLite 备份恢复。**部署前建议备份 `data/app.sqlite3`**（在 `start.sh`/Jenkinsfile 部署步骤加备份动作）。
4. 验证：登录「任务分析」页，确认任务列表摘要、编辑弹窗三 Tab、SMTP 折叠区、按任务推送历史、旧路由重定向、普通用户权限迁移后可访问。

## Open Questions

- 推送历史入口放在任务卡片按钮还是推送配置 Tab 内（或两者皆有）？设计建议两者皆有（卡片「推送历史」按钮 + Tab 内入口），实现时确认。
- `push_rules.task_ids` 孤儿列是否在本次直接 `DROP COLUMN`（SQLite ≥3.35 支持）？设计建议暂留，实现时按实际 SQLite 版本决定。
