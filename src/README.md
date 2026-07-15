# 信息智能分析系统 (InformationSmartAnalysisSystem)

针对给定信息源进行智能分析的系统。支持添加多种信息源、创建分析任务绑定信息源、展示信息源状态、触发分析（含基于新增内容的增量分析），分析调用大模型接口。

## 系统介绍

系统采用前后端分离架构，单服务部署：

- **后端**：Python 3.11 + FastAPI + Uvicorn，数据持久化使用 SQLite（SQLAlchemy ORM）。
- **前端**：Vue 3 + Vite + TypeScript + Element Plus，构建产物由后端静态托管。
- **大模型**：通过 OpenAI 兼容接口调用（base_url / api_key / model 均可配置）。
- **网页抓取**：使用集中的 WebFetch 服务（避免各系统重复实现抓取/反爬/缓存）。

核心能力：

1. 信息源管理：支持「官方网站」「指定本地文件夹」「FreshRSS 指定源」三类信息源。
2. 分析任务：创建任务并绑定多个信息源作为信息来源范围；展示每个绑定源的状态。
3. 增量分析：基于信息源新增内容做增量分析（按 (任务,源) 水位线记录已分析位置）；亦支持全量分析。
4. 基础模块：登录、权限管理、系统配置、任务中心（CLAUDE.md 规定必备）。

## 页面介绍

| 页面 | 路径 | 说明 | 权限键 |
|---|---|---|---|
| 登录 | `/login` | 用户名/密码登录 | 公开 |
| 概览 | `/dashboard` | 信息源/任务/最近运行概览 | `dashboard` |
| 信息源管理 | `/info-sources` | 三类信息源 CRUD、状态检查、手动同步、查看条目 | `info_sources` |
| 分析任务 | `/analysis-tasks` | 任务 CRUD、绑定源、查看源状态、触发全量/增量分析 | `analysis_tasks` |
| 分析结果 | `/analysis-result` | 查看分析产出（逐条/汇总） | `analysis_result` |
| 任务中心 | `/task-center` | 系统任务运行列表、状态、日志 | `task_center` |
| 权限管理 | `/permission` | 用户/角色、普通用户页面权限配置（仅管理员） | `permission`（仅 admin） |
| 系统配置 | `/system-config` | 展示 app.json（脱敏）与运行时信息 | `system_config` |

> 管理员默认拥有全部页面权限；普通用户的可见页面由管理员在「权限管理」页配置。

## 配置文件说明

主配置文件：`config/app.json`。所有环境相关信息（IP、端口、凭证、路径）均集中于此，代码中不硬编码。敏感字段（`secret_key`/`api_key`/`api_token` 等）可在「系统配置」页查看（已脱敏）。

| 配置项 | 说明 | 环境变量覆盖 |
|---|---|---|
| `server.host` / `server.port` | 监听地址与端口 | `ISAS_SERVER_HOST` / `ISAS_SERVER_PORT` |
| `database.path` | SQLite 数据库路径 | `ISAS_DB_PATH` |
| `auth.secret_key` | JWT 签名密钥（生产必须替换） | `ISAS_AUTH_SECRET_KEY` |
| `auth.token_expire_minutes` | Token 有效期（分钟） | `ISAS_TOKEN_EXPIRE_MINUTES` |
| `auth.password_file` | 用户密码文件路径 | `ISAS_PASSWORD_FILE` |
| `web_fetch.*` | WebFetch 服务地址与 API Key | `ISAS_WEB_FETCH_BASE_URL` / `ISAS_WEB_FETCH_API_KEY` |
| `llm.*` | 大模型接口（OpenAI 兼容） | `ISAS_LLM_BASE_URL` / `ISAS_LLM_API_KEY` / `ISAS_LLM_MODEL` |
| `logging.*` | 日志级别/目录/保留天数 | `ISAS_LOG_LEVEL` / `ISAS_LOG_DIR` |
| `worker.max_workers` | 后台任务线程数 | `ISAS_WORKER_MAX_WORKERS` |
| `data_dir` | 数据目录 | `ISAS_DATA_DIR` |

用户与角色维护在 `data/password.txt`（格式 `username:password:role`），修改后新用户在下次登录时自动同步到数据库。

### 信息源配置示例

- 官方网站：`{"url":"https://example.com/news","link_selector":"a.news","content_selector":"article","mode":"auto","max_items":20}`
- 本地文件夹：`{"folder_path":"/abs/path","patterns":["*.txt","*.md","*.pdf","*.docx","*.html"],"recursive":true,"max_items":50}`
- FreshRSS：`{"base_url":"http://freshrss.example.com","user":"admin","api_token":"<API Token>","stream":"user/-/state/com.google/reading-list","mark_as_read":false,"max_items":50}`

## 部署方式

### 首次部署

1. 准备运行环境：Python 3.11+（前端构建需 Node.js 18+ 与 npm）。
2. 执行启动脚本（脚本会自动创建 `data/`、`logs/`、默认 `password.txt`，创建虚拟环境并安装依赖，构建前端，启动服务）：
   - Windows：`.\src\start.ps1`
   - Linux/macOS：`bash src/start.sh`
3. 首次部署后，请修改 `data/password.txt` 中的默认口令与 `config/app.json` 中的 `auth.secret_key`、`llm.api_key` 等敏感配置。

> 自定义虚拟环境位置可设置环境变量 `ISAS_VENV`（默认 `src/.venv`）。

### 增量部署

- 重新拉取代码后再次执行启动脚本即可；脚本不会重复创建已存在的 `data/` 与 `password.txt`。
- 数据库表结构在服务启动时自动创建（`Base.metadata.create_all`）。

### Linux systemd 部署

服务单元文件：`JenkinsConfig/isas.service`。

```bash
sudo cp src/JenkinsConfig/isas.service /etc/systemd/system/isas.service
sudo systemctl daemon-reload
sudo systemctl enable --now isas
sudo systemctl status isas
```

> 请按实际部署路径调整 `isas.service` 中的 `WorkingDirectory` 与 `ExecStart`。

### Jenkins 部署

参见 `JenkinsConfig/Jenkinsfile` 与《生成Jenkinsfile的提示词.md》。流水线实现：停服 → 从 GitHub 拉取（SSH）→ 安装依赖/构建 → 启服，每 30 分钟轮询 GitHub 提交触发。

## 运维方式

| 操作 | Windows | Linux/macOS |
|---|---|---|
| 启动 | `.\src\start.ps1` | `bash src/start.sh` |
| 停止 | `.\src\stop.ps1` | `bash src/stop.sh` |
| 状态 | `.\src\status.ps1` | `bash src/status.sh` |

Linux 亦可使用 `systemctl start/stop/status/restart isas`。

日志按天切割于 `logs/`：当天为 `logs/app.log`，历史为 `logs/app.YYYY-MM-DD.log`；服务 PID 记录于 `logs/server.pid`。日志时间为北京时间。

下载的原始抓取文件按 `年/月/日` 存放于 `data/downloads/`。

## 访问方式

- 默认地址：`http://<服务器IP>:8000/`
- 健康检查：`http://<服务器IP>:8000/api/health`
- API 文档（Swagger）：`http://<服务器IP>:8000/docs`
- 默认账号：`admin / admin123`（首次部署后请立即修改 `data/password.txt`）

## 测试

```bash
cd src
.venv/Scripts/python -m pytest      # Windows
.venv/bin/python -m pytest          # Linux/macOS
```

包含单元测试（配置/鉴权/适配器/分析引擎/时间）与冒烟测试（端到端 API 流程），全部 mock 外部依赖，不依赖真实网络。

## 目录结构

```
src
├── app
│   ├── backend/        # FastAPI 后端
│   └── frontend/       # Vue 3 前端
├── config/app.json     # 主配置
├── data/               # 数据库、password.txt、downloads（运行时产物已 gitignore）
├── JenkinsConfig/      # Jenkinsfile + systemd 单元
├── tests/              # 单元 + 冒烟测试
├── logs/               # 日志（已 gitignore）
├── docs/               # 需求规格说明书、设计说明书
├── start.ps1 / start.sh / stop.* / status.*
└── README.md
```
