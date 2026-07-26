## 1. 配置与权限基础

- [ ] 1.1 在 `config/app.json` 新增 `email` 段（host/port/use_tls/use_ssl/username/password/from_email/from_name，值留空待部署方填写）
- [ ] 1.2 在 `core/config.py` 的 `Settings` 解析 `email` 段并支持 `ISAS_EMAIL_*` 环境变量覆盖
- [ ] 1.3 在 `core/pages.py` 的 `PAGE_DEFINITIONS` 增加 `push_management`（label「推送管理」，grantable=true）并验证 `ALL_PAGE_KEYS`/`GRANTABLE_PAGE_KEYS` 正确包含
- [ ] 1.4 编写测试：`email` 段解析、env 覆盖、`push_management` 页面注册（测试先行）

## 2. 数据模型

- [ ] 2.1 新建 `models/push.py`：`PushRule`（含 `task_ids`/`event_types`/`recipients` JSON、`trigger_mode`、`cron_expr`/`interval_seconds`、`enabled`、`last_pushed_result_id` 水位线、`channel`、`max_events_per_email`）、`PushRun`（历史）、`SmtpConfig`（单行 `id=1`）
- [ ] 2.2 在 `models/__init__.py` 注册新模型，确认 `init_db()` 的 `create_all` 能建出三张表
- [ ] 2.3 编写测试：模型字段默认值、`task_ids`/`event_types` JSON 读写、外键级联（`push_runs` 随 `push_rules` 删除）

## 3. SMTP 配置分层与测试连接

- [ ] 3.1 新建 `services/push/smtp_config.py`：`resolve_smtp_config()`（页面 `smtp_config` 表优先 -> `Settings.email_*` 回退 -> 缺最小必需项抛明确异常）
- [ ] 3.2 新建 `schemas/push.py` 的 SMTP 配置读写 schema（读取时 `password` 脱敏）
- [ ] 3.3 新建 `api/push.py` 的 SMTP 接口：`GET /api/push/smtp`、`PUT /api/push/smtp`（upsert `id=1`）、`POST /api/push/smtp/test`（同步发测试邮件并返回结果）
- [ ] 3.4 编写测试：页面优先于 app.json、回退 app.json、两处皆缺时报错、密码脱敏、测试邮件接口（用 mock SMTP）

## 4. 邮件渠道与渲染

- [ ] 4.1 新建 `services/push/channels/base.py` 定义 `PushChannel` 协议（`send(ctx, recipients, subject, html, text)`）
- [ ] 4.2 新建 `services/push/channels/email_channel.py` 的 `EmailChannel`（标准库 `smtplib`+`email.mime`，支持 TLS/SSL，UTF-8）
- [ ] 4.3 新建 `services/push/render.py`：把事件列表渲染为 HTML 正文（任务名/类型标签/来源/北京时间/内容）与纯文本备用，主题 `【信息分析】{rule_name} - {n}条新事件`
- [ ] 4.4 在 `services/push/channels/__init__.py` 维护 `CHANNELS = {"email": EmailChannel}` 注册表
- [ ] 4.5 编写测试：渲染含中文与北京时间、`EmailChannel` 发送（mock `smtplib.SMTP`）、渠道注册表按 key 取实现

## 5. 推送服务核心（增量水位线 + 分批 + 历史）

- [ ] 5.1 新建 `services/push/service.py` 的 `run_push(rule_id, trigger_mode)`：解析 SMTP -> 按水位线查增量事件 -> 分批渲染发送 -> 每批成功推进水位线 -> 写 `push_runs`（succeeded/failed/no_new）
- [ ] 5.2 实现 `on_analysis_completed(task_id)`：查询 `enabled AND trigger_mode='on_run' AND task_ids 含 task_id` 的规则并 `worker.submit(run_push, ...)`
- [ ] 5.3 编写测试：增量只推新事件、首次（水位线空）推全部匹配、按 `result_type`/`task_id` 筛选、分批发送、失败不推进水位线、无事件记 `no_new`（mock 渠道与 SMTP）

## 6. 触发集成

- [ ] 6.1 在 `services/scheduler.py` 暴露 `get_scheduler()` 访问器（保持现有行为不变）
- [ ] 6.2 新建 `services/push/push_scheduler.py`：用 job id `push-{rule_id}` 在共享调度器上 add/remove/reschedule `scheduled` 规则，回调 `worker.submit(run_push, rule_id, "scheduled")`；提供 `start_push_scheduler()` 加载已启用规则
- [ ] 6.3 在 `services/analysis/engine.py` 成功分支调用 `push_service.on_analysis_completed(task_id)`（try/except 吞异常仅记日志，不影响分析结果）
- [ ] 6.4 在 `main.py` 注册 `api/push.py` 路由，并在 lifespan 启动 `start_push_scheduler()`、停机时清理
- [ ] 6.5 编写测试：on_run 在分析成功后触发且失败不触发、`scheduled` 规则 add/remove/reschedule、停用规则后调度器移除、`scheduler.enabled=false` 时定时推送不可用但 on_run/手动可用

## 7. 推送规则 API

- [ ] 7.1 在 `schemas/push.py` 补全推送规则与历史 schema（创建/更新/输出）
- [ ] 7.2 在 `api/push.py` 实现规则 CRUD：`GET/POST/PUT/DELETE /api/push-rules`，`scheduled` 必填调度参数校验，CRUD 同步 `push_scheduler`
- [ ] 7.3 实现 `POST /api/push-rules/{id}/trigger`（手动触发，提交 worker 返回 202）与 `GET /api/push-rules/{id}/runs`（推送历史）
- [ ] 7.4 所有推送接口加 `Depends(require_page("push_management"))`
- [ ] 7.5 编写测试：CRUD、`scheduled` 缺参数返回 400、手动触发提交 worker、历史查询、未授权返回 403

## 8. 前端推送管理页

- [ ] 8.1 新建 `api/push.ts`：规则 CRUD、手动触发、历史、SMTP 配置读写、测试邮件
- [ ] 8.2 新建 `views/PushManagement.vue`：规则列表/新建编辑（选任务、事件类型、收件人、触发方式、调度参数）、启用停用、手动触发、推送历史
- [ ] 8.3 在 `views/PushManagement.vue` 内加 SMTP 配置区（保存、发送测试邮件、密码脱敏展示）
- [ ] 8.4 在 `router` 增加 `/push-management` 路由（`meta.page="push_management"`）并在 `layouts/MainLayout.vue` 增加菜单项
- [ ] 8.5 冒烟测试：建规则、配 SMTP、手动触发、查看历史（前端 `npm run build` 通过）

## 9. 文档、部署与验证

- [ ] 9.1 更新 `README.md`（推送管理页介绍、`email` 配置段说明、SMTP 配置方式、部署/运维注意事项）
- [ ] 9.2 更新需求规格说明书与设计说明书（推送功能需求与设计章节）
- [ ] 9.3 检查 `Jenkinsfile` 是否需调整（无新依赖则无需改动；确认流水线仍通过）
- [ ] 9.4 确认 `start.sh`/`start.ps1`/`status.sh`/`stop.sh`/systemd 单元无需因新功能改动（仅新增后端模块）
- [ ] 9.5 运行全部测试（`pytest`）与前端构建（`npm run build`）确认通过，并做一次端到端推送冒烟（配 SMTP -> 建规则 -> 手动触发 -> 收到邮件 -> 历史记录正确）
