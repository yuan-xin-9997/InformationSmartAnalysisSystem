# 邮件推送功能设计说明书

> 变更管理：完整需求规格 / 设计 / 任务见 OpenSpec 变更 `openspec/changes/add-email-push/`（proposal.md、specs/event-push/spec.md、design.md、tasks.md）。本文件为持久化设计摘要。

## 1. 概述

把增量分析结果（`AnalysisResult`，下称「事件」）按管理员配置的推送规则，通过邮件推送到指定邮箱。解决「分析结果只能登录系统查看」的问题，让关键分析产出主动送达。

- **事件** = 分析结果 `AnalysisResult`；事件类型 = `result_type`（`per_item` 逐条分析 / `aggregate` 汇总分析）。
- **增量** = 每条规则维护一个水位线 `last_pushed_result_id`（`AnalysisResult.id` 全局单调递增），只推送上次推送之后新生成的事件。
- **触发方式**（每条规则由用户选择）：① 分析任务完成后自动（`on_run`）；② 按计划定时（`scheduled`，cron/间隔）；③ 仅手动（`manual`）。
- **订阅** = 全局管理员配置；SMTP 配置页面优先于 `config/app.json` 的 `email` 段。

## 2. 数据模型（SQLite，建表由 `init_db()` 的 `create_all` 自动完成）

- `push_rules`：`name`、`channel`(默认 email)、`task_ids`(JSON)、`event_types`(JSON)、`recipients`(JSON)、`trigger_mode`、`cron_expr`、`interval_seconds`、`enabled`、`last_pushed_result_id`(水位线)、`max_events_per_email`(默认 50)。
- `push_runs`：推送历史，`rule_id`(级联删除)、`trigger_mode`、`recipients`、`event_count`、`status`(succeeded/failed/no_new)、`error`、`started_at`/`finished_at`/`created_at`。
- `smtp_config`：单行（`id=1`）SMTP 配置，覆盖 `app.json` 的 `email` 段。

## 3. 架构与执行流程

```
触发来源                        统一执行路径
─────────                      ──────────────
on_run  ──┐
scheduled ─┼──> worker.submit(run_push(rule_id, trigger_mode))
manual   ──┘            │
                        ▼
              resolve_smtp_config()      页面 > app.json > 报错
                        │
              查增量事件(id > 水位线, 按 task_ids/event_types 筛选)
                        │
              分批(max_events_per_email) render_events -> HTML+文本
                        │
              EmailChannel.send (stdlib smtplib+email, 无第三方依赖)
                        │
              每批成功推进水位线;失败不推进(下次重试)
                        │
              写 push_runs(succeeded/failed/no_new)
```

模块划分（`app/backend/services/push/`）：
- `smtp_config.py`：`resolve_smtp_config()` 分层解析器、`ResolvedSmtpConfig`、`SmtpConfigError`。
- `channels/base.py`：`PushChannel` Protocol（可扩展）。
- `channels/email_channel.py`：`EmailChannel`（标准库 SMTP 发送）。
- `channels/__init__.py`：`CHANNELS` 注册表 + `get_channel()`。
- `render.py`：`PushEvent` + `render_events()`（HTML 表格 + 纯文本，内容 HTML 转义，时间北京时间）。
- `service.py`：`run_push()`（核心执行）、`on_analysis_completed()`（on_run 钩子）。
- `push_scheduler.py`：`scheduled` 规则注册到共享 APScheduler（job id 命名空间 `push-{rule_id}`）。

## 4. 关键设计决策

1. **单值水位线**：`AnalysisResult.id` 全局单调，单值即可正确选出跨任务增量，无需按任务分记。
2. **分批发送 + 失败不推进**：`max_events_per_email` 分批，每批成功后推进水位线；任一批失败不推进，下次从该批重试（至少送达一次语义）。
3. **SMTP 配置分层**：页面 `smtp_config` 表优先 -> `Settings.email_*`（app.json）回退 -> 缺最小必需项（host+from_email）抛 `SmtpConfigError`；读取接口密码脱敏；PUT 时空密码保留旧值。
4. **触发集成复用现有机制**：on_run 在 `engine.run_analysis` 成功分支（`else`）调用钩子，异常隔离不影响分析；scheduled 复用 `scheduler.py` 的 `BackgroundScheduler`（经 `get_scheduler()` 访问器共享），不新建调度器；manual 经 worker 提交。
5. **可扩展渠道**：`PushChannel` Protocol + `CHANNELS` 注册表，新增渠道只需实现类并注册，规则与触发逻辑不动。
6. **不引入第三方依赖**：邮件用标准库 `smtplib`+`email.mime`；并发与调度复用现有 worker/APScheduler。

## 5. 配置

`config/app.json` 新增 `email` 段（值留空，由部署方填写或用页面配置）：

```json
"email": {
  "smtp_host": "", "smtp_port": 25, "use_tls": false, "use_ssl": false,
  "username": "", "password": "", "from_email": "", "from_name": "信息智能分析系统"
}
```

支持 `ISAS_EMAIL_*` 环境变量覆盖（见 README 配置表）。SMTP 凭据建议放 `config/env.local`（不被部署覆盖、不入 Git）。

## 6. 权限

新增页面权限键 `push_management`（`core/pages.py`，可授予）。所有推送 API 经 `require_page("push_management")` 拦截；管理员默认全放行，普通用户需管理员在「权限管理」页授予。

## 7. API（前缀 `/api/push`）

- SMTP：`GET/PUT /smtp`、`POST /smtp/test`
- 规则：`GET/POST /api/push/rules`、`PUT/DELETE /api/push/rules/{id}`、`POST /api/push/rules/{id}/trigger`、`GET /api/push/rules/{id}/runs`

## 8. 测试

单元测试覆盖：配置/页面注册、模型、SMTP 分层（优先/回退/报错/脱敏/测试邮件）、渠道与渲染、推送服务（增量/首次/筛选/分批/失败不推进/no_new/on_run 触发）、调度集成、规则 API（CRUD/校验/触发/历史/403）；冒烟测试覆盖端到端推送流程（配 SMTP -> 建规则 -> 手动触发 -> 历史正确）。全部 mock 外部依赖，不依赖真实 SMTP/网络。
