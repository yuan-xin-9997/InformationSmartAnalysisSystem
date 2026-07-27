## 架构要求

1. 优先基于 Python 语言开发，后端架构使用 Fastapi、前端架构使用 Vue。
2. 数据库优先使用轻量数据库 SQLite，如果要开发的系统不适合 SQLite，需要给出理由并经过审批才能更换。
3. 如果涉及到网页抓取，优先使用集中的网页抓取服务，API Key 是966f9d9f573e6efcb889b5fe9bfe48b6c528e4a08ebddc3ffcbd5c49406a9fa9，服务地址：[http://192.168.0.111:33333/](http://192.168.0.111:33333/health/ready)，健康检查http://192.168.0.111:33333/health/ready，接口文档[WebFetch Service - Swagger UI](http://192.168.0.111:33333/docs)，READMEhttps://github.com/yuan-xin-9997/web_fetch/blob/main/README.md

## 基本模块或功能要求

以下是系统必须包含的基本模块，哪怕用户在需求中没有明确提到。

1. 登录功能：系统支持不同用户登录，可以登录的用户名和密码维护在 password.txt 中。
2. 权限管理模块：用于维护可登录本系统的用户信息，包含用户名、角色（管理员、普通用户）、可访问的页面。
3. 系统配置模块：显示当前系统的配置，包括配置在配置文件中的配置。
4. 任务中心模块：显示当前系统的任务列表、任务日志、任务状态等

## 代码目录结构要求

项目大体按照如下目录结构开发：

src

├── app # 前后端代码目录

├── config # 配置文件目录

│   └── app.json # 系统主配置文件，JSON 格式

├── data # 数据目录

│   ├── app.sqlite3 # SQLite 数据文件

│   └── password.txt # 用户密码信息

├── JenkinsConfig # 存放 Jenkins 相关文件

│ ├── Jenkinsfile # Jenkins 流水线文件

├── tests # 测试脚本

├── logs # 日志目录

│   ├── app.log # 当天的日志

│   ├── app.xxxx-xx-xx.log # 历史日志，按天自动切割

│   └── server.pid # 当前系统的主进程 PID

├── README.md # 自述文件

├── start.ps1 # Windows 启动系统脚本

├── start.sh # Linux 启动系统脚本

├── status.ps1 # Windows 显示系统状态脚本

├── status.sh # Linux 显示系统状态脚本

├── stop.ps1 # Windows 停止系统脚本

└── stop.sh # Linux 停止系统脚本

## 开发规范

1. 禁止在代码中硬编码任何环境相关信息，比如 IP、端口、用户名、密码、绝对路径等信息。这些必须可配置
2. 系统显示的时间如果不是北京时间，需要在原始时间的基础上显示北京时间
3. 若有下载的文件需要按年份/月份/天保存在 data 目录
4. 项目 .gitignore 文件要包含 logs 目录，但是不能包含 data 目录

## 测试要求

1. 所有功能必须做基本的单元测试、冒烟测试等，测试必须都通过

## 部署要求

1. 首次部署的时候，需要创建 data 目录，并创建 password.txt，添加附件提到的默认内容。后续增量部署则不需要重复创建 data 目录
2. 在完成自测之后，交付给我之前，需要将项目整合到 Jenkins 中，参照“生成Jenkinsfile的提示词.md”执行部署
3. 如果部署在Linux系统上，则还需要支持systemd的方式进行系统的启停、状态检查。

## 文档要求

1. README.md 文件需要包含系统介绍、页面介绍、配置文件说明、部署方式、运维方式、访问方式等章节，且需要及时更新
2. 需求规格说明书、设计说明书需要及时更新

## 需求新增或变更的要求

1. 若用户有需求新增或变更，在开发自测完后，需要根据情况更新需求规格说明书、设计说明书、README.md、Jenkinsfile 等文件
2. 在提交到 Github 之后，需要手动触发 Jenkins 的手工构建，并让用户访问手工构建之后的服务，以验证新增或变更的功能是否符合预期

## 附件

### password.txt 默认内容

```
# 格式: username:password:role  (role 取值: admin | user)
# admin 默认拥有所有页面权限；user 的可见页面由管理员在权限管理页配置。
# 修改本文件后，新用户在下次登录时会自动同步到数据库。
admin:admin123:admin
```

<!-- superpowers-zh:begin (do not edit between these markers) -->
# Superpowers-ZH 中文增强版

本项目已安装 superpowers-zh 技能框架（20 个 skills）。

## 核心规则

1. **收到任务时，先检查是否有匹配的 skill** — 哪怕只有 1% 的可能性也要检查
2. **设计先于编码** — 收到功能需求时，先用 brainstorming skill 做需求分析
3. **测试先于实现** — 写代码前先写测试（TDD）
4. **验证先于完成** — 声称完成前必须运行验证命令

## 可用 Skills

Skills 位于 `.claude/skills/` 目录，每个 skill 有独立的 `SKILL.md` 文件。

- **brainstorming**: 在任何创造性工作之前必须使用此技能——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。
- **chinese-code-review**: 中文 review 沟通参考——话术模板、分级标注（必须修复/建议修改/仅供参考）、国内团队常见反模式应对。仅在用户显式 /chinese-code-review 时调用，不要根据上下文自动触发。
- **chinese-commit-conventions**: 中文 commit 与 changelog 配置参考——Conventional Commits 中文适配、commitlint/husky/commitizen 中文模板、conventional-changelog 中文配置。仅在用户显式 /chinese-commit-conventions 时调用，不要根据上下文自动触发。
- **chinese-documentation**: 中文文档排版参考——中英文空格、全半角标点、术语保留、链接格式、中文文案排版指北约定。仅在用户显式 /chinese-documentation 时调用，不要根据上下文自动触发。
- **chinese-git-workflow**: 国内 Git 平台配置参考——Gitee、Coding.net、极狐 GitLab、CNB 的 SSH/HTTPS/凭据/CI 接入差异与镜像同步配置。仅在用户显式 /chinese-git-workflow 时调用，不要根据上下文自动触发。
- **dispatching-parallel-agents**: 当面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用
- **executing-plans**: 当你有一份书面实现计划需要在单独的会话中执行，并设有审查检查点时使用
- **finishing-a-development-branch**: 当实现完成、所有测试通过、需要决定如何集成工作时使用——通过提供合并、PR 或清理等结构化选项来引导开发工作的收尾
- **mcp-builder**: MCP 服务器构建方法论 — 系统化构建生产级 MCP 工具，让 AI 助手连接外部能力
- **receiving-code-review**: 收到代码审查反馈后、实施建议之前使用，尤其当反馈不明确或技术上有疑问时——需要技术严谨性和验证，而非敷衍附和或盲目执行
- **requesting-code-review**: 完成任务、实现重要功能或合并前使用，用于验证工作成果是否符合要求
- **subagent-driven-development**: 当在当前会话中执行包含独立任务的实现计划时使用
- **systematic-debugging**: 遇到任何 bug、测试失败或异常行为时使用，在提出修复方案之前执行
- **test-driven-development**: 在实现任何功能或修复 bug 时使用，在编写实现代码之前
- **using-git-worktrees**: 当需要开始与当前工作区隔离的功能开发，或在执行实现计划之前使用——通过原生工具或 git worktree 回退机制确保隔离工作区存在
- **using-superpowers**: 在开始任何对话时使用——确立如何查找和使用技能，要求在任何响应（包括澄清性问题）之前调用 Skill 工具
- **verification-before-completion**: 在宣称工作完成、已修复或测试通过之前使用，在提交或创建 PR 之前——必须运行验证命令并确认输出后才能声称成功；始终用证据支撑断言
- **workflow-runner**: 在 Claude Code / OpenClaw / Cursor 中直接运行 agency-orchestrator YAML 工作流——无需 API key，使用当前会话的 LLM 作为执行引擎。当用户提供 .yaml 工作流文件或要求多角色协作完成任务时触发。
- **writing-plans**: 当你有规格说明或需求用于多步骤任务时使用，在动手写代码之前
- **writing-skills**: 当创建新技能、编辑现有技能或在部署前验证技能是否有效时使用

## 如何使用

当任务匹配某个 skill 时，使用 `Skill` 工具加载对应 skill 并严格遵循其流程。绝不要用 Read 工具读取 SKILL.md 文件。

如果你认为哪怕只有 1% 的可能性某个 skill 适用于你正在做的事情，你必须调用该 skill 检查。
<!-- superpowers-zh:end -->
