# 执行计划：add-email-push

> 使用 Superpowers `executing-plans` 技能执行 `openspec/changes/add-email-push/tasks.md`。
> 本文件是对 tasks.md 的**执行策略**（方法论、节奏、验证门、审查检查点、子代理编排、收尾），不重复 tasks.md 的任务清单本身。

## 0. 方法论与前置

- **方法论（Superpowers）**：每个任务组走 TDD 循环——先写测试（红）→ 实现（绿）→ 重构；每组结束跑验证门；按组提交、commit message 引用任务编号；遇阻用 `systematic-debugging`；声明完成前用 `verification-before-completion`。
- **分支**：从 `main` 新建 `feature/add-email-push`（携带当前未跟踪的 openspec 产物，tasks.md 随手可得）。首个 commit 提交 openspec 变更产物（proposal/design/specs/tasks）作为基线。
- **环境**：后端 Python 3.13 + `src/.venv`；测试 `cd src && python -m pytest`（`pytest.ini` 已设 `pythonpath=.`、`testpaths=tests`）；前端 `cd src/app/frontend && npm run build`（vue-tsc 类型检查 + vite 构建）。
- **验证策略**：自动化测试用 mock `smtplib.SMTP`（无真实发信、无外部依赖）；任务 9.5 通过校验 `push_runs` 历史（status/event_count）验证全链路；真实发信留作可选手动步骤（你提供 SMTP 凭据时再做）。
- **依赖**：不引入第三方依赖，邮件用标准库 `smtplib`+`email.mime`。
- **提交/推送**：按组提交、引用任务编号；**不 push**，除非你明确要求。

## 1. 执行序列（每组 TDD：测试先行）

每组节奏：`[标进行中] → 写测试并跑(红) → 实现 → 跑验证门(绿) → commit(引用任务号) → 标完成`。测试文件落在 `src/tests/unit/`，命名 `test_push_*.py`，复用 `conftest.py` 的 `client`/`admin_headers`/`sync_worker`/`mock_llm` fixture。

| 组 | 内容 | 验证门（命令） | commit 主题 |
|----|------|----------------|------------|
| 1 | 配置与权限基础：`app.json` email 段、`core/config.py` 解析+`ISAS_EMAIL_*`、`core/pages.py` 加 `push_management`、测试 | `cd src && python -m pytest tests/unit/test_config.py tests/unit/test_pages.py -q` | `feat(push): email配置段与push_management页面权限 (任务1.x)` |
| 2 | 数据模型：`models/push.py`（PushRule/PushRun/SmtpConfig）、`models/__init__` 注册、测试 | `cd src && python -m pytest tests/unit/test_push_model.py -q` | `feat(push): 推送规则/历史/SMTP模型 (任务2.x)` |
| 3 | SMTP 配置分层：`services/push/smtp_config.py`、schemas、`api/push.py` SMTP 接口、测试（优先级/回退/缺项报错/脱敏/测试邮件） | `cd src && python -m pytest tests/unit/test_smtp_config.py tests/unit/test_push_smtp_api.py -q` | `feat(push): SMTP配置分层与测试连接 (任务3.x)` |
| 4 | 邮件渠道：`channels/base.py` 协议、`email_channel.py`、`render.py`、注册表、测试（渲染中文/北京时间、mock 发送、注册表） | `cd src && python -m pytest tests/unit/test_push_channels.py tests/unit/test_push_render.py -q` | `feat(push): 邮件渠道与渲染 (任务4.x)` |
| 5 ★ | 推送服务核心：`services/push/service.py` 的 `run_push`（水位线/分批/历史）、`on_analysis_completed`、测试（增量/首次/筛选/分批/失败不推进/no_new） | `cd src && python -m pytest tests/unit/test_push_service.py -q` | `feat(push): 增量推送服务核心 (任务5.x)` |
| 6 | 触发集成：`scheduler.get_scheduler()`、`services/push/push_scheduler.py`、engine on_run 钩子、`main.py` lifespan、测试 | `cd src && python -m pytest tests/unit/test_push_scheduler.py tests/unit/test_engine.py -q` | `feat(push): 三种触发集成 (任务6.x)` |
| 7 | 推送规则 API：schemas、CRUD/trigger/history、`require_page("push_management")`、测试（CRUD/校验/403） | `cd src && python -m pytest tests/unit/test_push_api.py -q` | `feat(push): 推送规则与历史API (任务7.x)` |

**【审查检查点 1】** 组 7 完成后暂停：后端全链路就绪，跑 `cd src && python -m pytest -q` 全绿后，向你汇报后端实现要点与测试结果，等你确认再进前端。

| 组 | 内容 | 验证门 | commit 主题 |
|----|------|--------|------------|
| 8 | 前端推送管理页：`api/push.ts`、`views/PushManagement.vue`（规则/SMTP/手动触发/历史）、router+菜单、冒烟 | `cd src/app/frontend && npm run build` | `feat(push): 推送管理页 (任务8.x)` |
| 9 | 文档与验证：README、需求/设计说明书、Jenkinsfile/脚本检查、全量测试+端到端冒烟（mock，校验 push_runs 历史） | `cd src && python -m pytest -q` + 前端构建 | `docs(push): 文档与端到端验证 (任务9.x)` |

**【审查检查点 2】** 组 9 完成、全量测试与前端构建均通过后，进入收尾。

## 2. 子代理编排

- **核心后端（组 2–7）**：主会话直接执行（TDD、跨文件一致性强、fixture 约定多，不宜分派）。
- **独立块（可派发子代理并行）**：
  - 组 8 前端页面——在后端 API 契约固定后派发一个子代理实现 `PushManagement.vue`+`api/push.ts`（我提供 API 契约清单与现有页面范式参照）。
  - 组 9.1/9.2 文档——派发子代理并行更新 README 与需求/设计说明书（我提供变更摘要）。
- 主会话始终负责：跑验证门、合并子代理产出后回测、提交。

## 3. 关键技术约束（执行时严格遵守）

- 水位线为单值 `last_pushed_result_id`（`AnalysisResult.id` 全局单调递增，跨任务也正确）。
- 分批发送（`max_events_per_email` 默认 50），每批成功后推进水位线；任一批失败不推进、剩余批停止（下次重试）。
- SMTP 配置解析顺序：页面 `smtp_config` 表 → `Settings.email_*`（app.json）→ 缺最小必需项抛明确异常；读取接口 `password` 脱敏（复用 `core/secrets.py`）。
- engine 的 on_run 钩子用 try/except 吞异常仅记日志，**不得影响已成功的分析**。
- 定时推送复用 `scheduler.py` 的同一个 `BackgroundScheduler`，job id 命名空间 `push-{rule_id}`；`scheduler.enabled=false` 时定时不可用，但 on_run 与手动可用。
- 不硬编码任何环境信息（IP/端口/凭据/绝对路径），全部走配置；时间显示用 `core/timeutil` 转北京时间。

## 4. 收尾（finishing-a-development-branch）

组 9 通过后：
1. 宣布使用 `finishing-a-development-branch` 技能。
2. 终态验证：`cd src && python -m pytest -q` 全绿 + `cd src/app/frontend && npm run build` 通过 + 端到端冒烟（mock）push_runs 历史正确。
3. 按 finishing 技能展示选项（合并到 main / 发 PR / 保留分支）由你选择；**不 push、不合并**除非你明确授权。
4. 产出执行报告（完成/偏离/验证结果/下一步）。

## 5. 阻塞时停下的条件

- 同一测试失败 2 次以上、依赖缺失、指令不清、计划描述与实际冲突 → 停下报告，不猜测。
- 发现 tasks.md/design.md 需修正 → 停下与你确认后再改计划。
