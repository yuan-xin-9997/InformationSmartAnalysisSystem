# Implementation Tasks

## 1. 数据模型与迁移

- [x] 1.1 修改 `src/app/backend/models/push.py`：`PushRule` 新增 `task_id` 外键字段（`ForeignKey("analysis_tasks.id", ondelete="CASCADE")`，可空以兼容迁移期），移除业务代码对 `task_ids` 的使用（DB 旧列 `task_ids` 暂留为孤儿列被忽略）；更新关系与 `__all__`。
- [x] 1.2 修改 `src/app/backend/models/scheduled_job.py`：保持 `ScheduledJob` 表结构不变（1:1 由服务层 upsert + 迁移期唯一索引保证），确认 `task_id` 外键与 `task` 关系保留。
- [x] 1.3 修改 `src/app/backend/core/database.py` 的 `init_db()`：追加 `_ensure_column(engine, "push_rules", "task_id", "INTEGER")`；新增幂等函数 `_migrate_consolidate_task_analysis(engine)`--拆分多任务推送规则（按决策 6 复制水位线）、回填单任务规则 `task_id`、按 `task_id` 收敛多余定时（保留最新一条）、迁移用户权限（补 `analysis_tasks` 移除 `scheduled_jobs`/`push_management`）、去重后 `CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_jobs_task_id` 与 `uq_push_rules_task_id`；用「`task_ids` 非空且 `task_id` 为空」作为旧规则哨兵保证幂等。
- [x] 1.4 编写迁移单测 `src/tests/unit/test_consolidate_migration.py`：多任务规则拆分且水位线原样复制、单任务回填、多余定时收敛、用户权限迁移、唯一索引创建成功、跑两次幂等结果一致。

## 2. 后端 Schemas

- [x] 2.1 修改 `src/app/backend/schemas/`（analysis 相关）：`AnalysisTaskDetail` 附带 `schedule` 与 `push` 完整配置；`AnalysisTaskListItem` 附带 `schedule_summary` 与 `push_summary`（启用状态、调度描述、收件人数、触发方式）；新增 `ScheduleConfig`、`PushConfig` 的 upsert schema。
- [x] 2.2 新增/调整 `PUT /api/analysis-tasks/{id}` 的请求 schema：`schedule`/`push` 为可选，传 `null` 表示删除该子配置，传对象表示 upsert。
- [x] 2.3 移除不再需要的 `scheduled_jobs`、`push rules` 独立 CRUD schema（保留 SMTP 相关 schema）。

## 3. 后端 API

- [x] 3.1 修改 `src/app/backend/api/analysis_tasks.py`：`GET /api/analysis-tasks` 列表项附带 schedule/push 摘要；`GET /api/analysis-tasks/{id}` 详情附带完整 schedule/push；`PUT /api/analysis-tasks/{id}` 在单事务内 upsert 任务/调度/推送（`null`=删除子配置），任一失败整体回滚。
- [x] 3.2 新增任务维度端点：`POST /api/analysis-tasks/{id}/schedule/run`（立即执行定时分析）、`POST /api/analysis-tasks/{id}/push/trigger`（手动推送）、`GET /api/analysis-tasks/{id}/push/runs`（按任务推送历史）。
- [x] 3.3 修改 `src/app/backend/api/push.py`：保留 `/api/push/smtp`（GET/PUT/发送测试），移除 `/api/push/rules/*` 端点；修改 `src/app/backend/api/scheduled_jobs.py`：移除旧 `/api/scheduled-jobs/*` 端点（或删除该模块）。
- [x] 3.4 更新 `src/app/backend/api/__init__.py`/`main.py` 路由注册：移除已删路由，注册新任务维度端点。

## 4. 后端服务适配

- [x] 4.1 修改 `src/app/backend/services/scheduler.py`：`ScheduledJob` 1:1 适配--按 `task_id` upsert 时同步调度器注册/更新；启用/停用、立即执行、`next_run_at` 计算语义不变。
- [x] 4.2 修改 `src/app/backend/services/push/service.py` 与 `push_scheduler.py`：推送筛选由 `task_id IN (rule.task_ids)` 改为 `task_id == rule.task_id`；`on_run`/`scheduled`/`manual` 三种触发的增量水位线语义不变；定时推送调度按 1:1 注册。
- [x] 4.3 核对 `src/app/backend/services/analysis/engine.py` 的 `on_run` 钩子：确认任务运行成功后按其 `task_id` 查找 1:1 推送配置并触发自动推送的逻辑正确；失败不触发不变。

## 5. 前端统一页

- [x] 5.1 重构 `src/app/frontend/src/views/AnalysisTasks.vue` 为「任务分析」页：任务列表卡片新增「定时/推送」状态摘要；编辑弹窗改为 Tab 分区（基本信息/定时分析/推送配置）且每 Tab 标题带状态徽标；保存统一提交三区。
- [x] 5.2 在「任务分析」页底部新增全局「邮件通道（SMTP）」折叠区（默认折叠），承载原 SMTP 配置/保存/测试。
- [x] 5.3 在「任务分析」页新增「按任务推送历史」弹窗（任务卡片按钮 + 推送配置 Tab 内入口），调用 `GET /api/analysis-tasks/{id}/push/runs`。
- [x] 5.4 修改 `src/app/frontend/src/api/tasks.ts`：类型与方法适配一体化端点（list/get 附带 schedule/push、save 含 schedule/push、`schedule/run`、`push/trigger`、`push/runs`、SMTP 沿用）。
- [x] 5.5 清理 `src/app/frontend/src/api/scheduledJobs.ts`、`api/push.ts`：移除已删端点调用，SMTP 相关保留或并入 `tasks.ts`。
- [x] 5.6 删除 `src/app/frontend/src/views/ScheduledJobs.vue` 与 `PushManagement.vue`（能力已并入统一页）。

## 6. 权限与路由收敛

- [x] 6.1 修改 `src/app/backend/core/pages.py`：`PAGE_DEFINITIONS` 移除 `scheduled_jobs`、`push_management`；`analysis_tasks` 的 `label` 改为「任务分析」。
- [x] 6.2 修改 `src/app/frontend/src/router/index.ts`：`/analysis-tasks` 路由 `meta.title` 改「任务分析」；`/scheduled-jobs`、`/push-management` 改为重定向到 `/analysis-tasks`；移除对应组件路由。
- [x] 6.3 修改 `src/app/frontend/src/layouts/MainLayout.vue`：`allMenus`/`pageMeta` 移除「定时任务」「推送管理」入口，「分析任务」改「任务分析」。
- [x] 6.4 核对前端鉴权/权限页（`stores/auth.ts`、`views/Permission.vue`）无硬编码旧页面键，与新 `pages.py` 一致。

## 7. 测试

- [x] 7.1 后端单测 `src/tests/unit/`：1:1 schedule/push upsert（重复保存更新不新增）、`PUT` 一体化保存事务回滚、`null` 删除子配置、按任务历史、立即执行/手动触发端点。
- [x] 7.2 后端回归：`on_run` 自动推送、定时调度、水位线推进、SMTP 分层优先与密码脱敏、未授权 403。
- [x] 7.3 前端冒烟：`npm run build` 通过；手工验证三 Tab 配置与一次保存、任务列表状态摘要、SMTP 折叠区、按任务推送历史、旧路由重定向、普通用户权限迁移后可访问。
- [x] 7.4 迁移冒烟：在含多任务规则/多余定时/旧权限的旧 `app.sqlite3` 上启动，验证拆分/收敛/权限/唯一索引结果正确，且重复启动幂等。

## 8. 文档与部署

- [x] 8.1 更新 `README.md`：页面介绍改为三页合一「任务分析」、编辑弹窗三分区、SMTP 全局折叠区、权限与路由变化、迁移与备份说明。
- [x] 8.2 更新需求规格说明书、设计说明书（统一页、1:1 模型、迁移、权限收敛）。
- [x] 8.3 评估 `Jenkinsfile`/`start.sh`：部署前备份 `data/app.sqlite3`（迁移不可逆）；无依赖/启动方式变化则不改启动逻辑。
- [ ] 8.4 提交 Github，手动触发 Jenkins 构建，访问服务验证三页合一功能；通过后归档 openspec 变更（`/opsx:archive`）。
