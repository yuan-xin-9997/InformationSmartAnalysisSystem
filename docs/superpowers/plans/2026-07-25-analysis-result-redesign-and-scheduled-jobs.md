# 分析结果页改造与定时任务 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 删除独立「分析结果」菜单页、改为从分析任务下钻的任务结果详情页；新增「定时任务」页面，支持 cron/间隔调度自动触发分析。

**架构：** 后端 FastAPI + SQLite(SQLAlchemy)。定时任务用 APScheduler `BackgroundScheduler`（进程内，时区 `Asia/Shanghai`），到点创建 `TaskRun` 并复用现有 `worker.submit(run_analysis, ...)` 链路。前端 Vue3 + Element 风格原生组件，新增 `TaskResults.vue`（按运行批次分组+折叠展开 Markdown）与 `ScheduledJobs.vue`。

**技术栈：** Python 3.11 / FastAPI / SQLAlchemy 2.x / apscheduler 3.10 / pytest；Vue 3 + Vite + TS。

**运行约定：** 后端测试与启动均在 `src/` 目录下执行（`main.py` 顶部注释）。前端在 `src/app/frontend/` 下。pytest 配置见 `src/pytest.ini`。

**设计规格：** `docs/superpowers/specs/2026-07-25-analysis-result-redesign-and-scheduled-jobs-design.md`

---

## 文件结构

### 新建
| 文件 | 职责 |
|---|---|
| `src/app/backend/models/scheduled_job.py` | `ScheduledJob` ORM 模型 |
| `src/app/backend/schemas/scheduled_job.py` | 定时任务 Pydantic 入参/出参 |
| `src/app/backend/services/scheduler.py` | APScheduler 单例：启停/CRUD 同步/`_fire` 触发 |
| `src/app/backend/api/scheduled_jobs.py` | 定时任务 REST 端点 |
| `src/app/backend/tests/unit/test_scheduled_jobs.py` | 定时任务单元测试 |
| `src/app/frontend/src/views/TaskResults.vue` | 任务结果详情页（按批次分组） |
| `src/app/frontend/src/views/ScheduledJobs.vue` | 定时任务管理页 |
| `src/app/frontend/src/api/scheduledJobs.ts` | 定时任务前端 API 封装 |

### 修改
| 文件 | 改动 |
|---|---|
| `src/app/backend/models/task.py` | `TaskRun` 加 `scheduled_job_id` 列 |
| `src/app/backend/models/__init__.py` | 注册 `ScheduledJob` |
| `src/app/backend/core/database.py` | 加 `_ensure_column` 轻量迁移；`init_db` 迁移 `task_runs.scheduled_job_id` |
| `src/app/backend/core/pages.py` | 删 `analysis_result`；增 `scheduled_jobs` |
| `src/app/backend/core/config.py` | 增 `scheduler_*` 字段 |
| `src/config/app.json` | 增 `scheduler` 段 |
| `src/config/env.local.example` | 增 scheduler 覆盖示例 |
| `src/app/backend/requirements.txt` | 增 `apscheduler>=3.10` |
| `src/app/backend/services/analysis/engine.py` | `run_analysis` 结束回写 `scheduled_job.last_run_status` |
| `src/app/backend/api/analysis_tasks.py` | 删 `results_router`/`list_results` |
| `src/app/backend/api/task_center.py` | `list_runs` 增 `ref_id` 过滤 |
| `src/app/backend/main.py` | lifespan 启停调度器；挂载 scheduled_jobs 路由；移除 results_router |
| `src/app/frontend/src/router/index.ts` | 删 `/analysis-result`；增 `/analysis-tasks/:id/results` 与 `/scheduled-jobs` |
| `src/app/frontend/src/layouts/MainLayout.vue` | 删「分析结果」菜单；增「定时任务」菜单 |
| `src/app/frontend/src/views/AnalysisTasks.vue` | `goResults` 改跳新路由；可选显示「已配 N 个定时」 |
| `src/app/frontend/src/api/tasks.ts` | 删 `listAllResultsApi` |
| `src/tests/smoke/test_flow.py` | 增定时任务与结果详情页冒烟 |
| `src/docs/需求规格说明书.md`、`src/docs/设计说明书.md`、`src/README.md` | 文档同步 |

### 删除
- `src/app/frontend/src/views/AnalysisResult.vue`

---

## 阶段 A：需求1 - 分析结果改为任务下钻详情页

### 任务 A1：task_center.list_runs 增加 ref_id 过滤

**文件：**
- 修改：`src/app/backend/api/task_center.py:17-30`
- 测试：`src/tests/unit/test_task_center.py`（新建）

- [ ] **步骤 1：编写失败的测试**

新建 `src/tests/unit/test_task_center.py`：

```python
"""task_center list_runs filtering tests."""
from __future__ import annotations


def test_list_runs_filter_by_ref_id(client, admin_headers, sync_worker, mock_llm):
    # 建一个信息源 + 任务，触发一次分析产生 run
    src = client.post(
        "/api/info-sources",
        json={"name": "s1", "type": "local_folder", "config": {"folder_path": "."}},
        headers=admin_headers,
    )
    assert src.status_code == 201, src.text
    sid = src.json()["id"]
    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t1", "config": {"mode": "per_item"}, "source_ids": [sid]},
        headers=admin_headers,
    )
    assert t.status_code == 201, t.text
    tid = t.json()["id"]
    run = client.post(f"/api/analysis-tasks/{tid}/run", json={"mode": "incremental"}, headers=admin_headers)
    assert run.status_code == 200, run.text
    rid = run.json()["run_id"]

    # 按 ref_id 过滤只返回该任务的 run
    r = client.get(f"/api/task-center/runs?kind=analysis&ref_id={tid}", headers=admin_headers)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert rid in ids
    assert all(x["ref_id"] == tid for x in r.json())
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_task_center.py -v`
预期：FAIL，`ref_id` 参数被忽略（返回所有 run，断言 `all(...)` 失败）。

- [ ] **步骤 3：实现 ref_id 过滤**

修改 `src/app/backend/api/task_center.py` 的 `list_runs`，在 `kind` 参数后增加 `ref_id`：

```python
@router.get("/runs", response_model=list[TaskRunOut])
def list_runs(
    kind: str | None = Query(None, description="analysis | sync"),
    ref_id: int | None = Query(None),
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_page("task_center")),
    db: Session = Depends(get_db),
):
    q = select(TaskRun).order_by(TaskRun.created_at.desc()).limit(limit)
    if kind:
        q = q.where(TaskRun.kind == kind)
    if ref_id is not None:
        q = q.where(TaskRun.ref_id == ref_id)
    if status_:
        q = q.where(TaskRun.status == status_)
    return db.scalars(q).all()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd src && pytest tests/unit/test_task_center.py -v`
预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add src/app/backend/api/task_center.py src/tests/unit/test_task_center.py
git commit -m "任务中心: list_runs 支持 ref_id 过滤"
```

---

### 任务 A2：删除全局分析结果端点 + pages.py 删 analysis_result

**文件：**
- 修改：`src/app/backend/api/analysis_tasks.py`（删 `results_router` 与 `list_results`、`_result_out` 保留供 task results 用）
- 修改：`src/app/backend/main.py:66`（删 `include_router(results_router)`）
- 修改：`src/app/backend/core/pages.py`（删 `analysis_result`）
- 测试：`src/tests/unit/test_pages.py`（新建）

- [ ] **步骤 1：编写失败的测试**

新建 `src/tests/unit/test_pages.py`：

```python
"""Page key registry tests."""
from __future__ import annotations

from app.backend.core.pages import ALL_PAGE_KEYS, GRANTABLE_PAGE_KEYS


def test_analysis_result_removed():
    assert "analysis_result" not in ALL_PAGE_KEYS
    assert "analysis_result" not in GRANTABLE_PAGE_KEYS


def test_scheduled_jobs_present():
    assert "scheduled_jobs" in ALL_PAGE_KEYS
    assert "scheduled_jobs" in GRANTABLE_PAGE_KEYS
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_pages.py -v`
预期：FAIL（`analysis_result` 仍在；`scheduled_jobs` 不在）。

- [ ] **步骤 3：修改 pages.py**

修改 `src/app/backend/core/pages.py`：删除 `analysis_result` 行，新增 `scheduled_jobs`：

```python
PAGE_DEFINITIONS: list[dict[str, str | bool]] = [
    {"key": "dashboard", "label": "概览", "grantable": True},
    {"key": "info_sources", "label": "信息源管理", "grantable": True},
    {"key": "analysis_tasks", "label": "分析任务", "grantable": True},
    {"key": "scheduled_jobs", "label": "定时任务", "grantable": True},
    {"key": "task_center", "label": "任务中心", "grantable": True},
    {"key": "system_config", "label": "系统配置", "grantable": True},
    {"key": "permission", "label": "权限管理", "grantable": False},  # admin only
]
```

- [ ] **步骤 4：删除全局结果端点**

修改 `src/app/backend/api/analysis_tasks.py`：
- 删除模块顶部 `results_router = APIRouter(prefix="/api/analysis-results", tags=["分析结果"])`。
- 删除 `list_results` 函数（原 `@results_router.get("")` 那个）。
- 保留 `_result_out` 与 `list_task_results`（任务结果详情页用）。

修改 `src/app/backend/main.py`：删除 `app.include_router(analysis_tasks_api.results_router)` 这一行。

- [ ] **步骤 5：运行测试验证通过**

运行：`cd src && pytest tests/unit/test_pages.py -v && pytest tests/smoke/test_flow.py -v`
预期：PASS（`test_pages` 通过；现有冒烟不应调用已删端点，仍通过）。

- [ ] **步骤 6：Commit**

```bash
git add src/app/backend/core/pages.py src/app/backend/api/analysis_tasks.py src/app/backend/main.py src/tests/unit/test_pages.py
git commit -m "分析结果: 删除全局结果端点与 analysis_result 权限键,新增 scheduled_jobs 键"
```

---

### 任务 A3：前端 - 新建 TaskResults.vue + 路由/菜单调整 + 删除旧页

**文件：**
- 新建：`src/app/frontend/src/views/TaskResults.vue`
- 修改：`src/app/frontend/src/router/index.ts`
- 修改：`src/app/frontend/src/layouts/MainLayout.vue`
- 修改：`src/app/frontend/src/views/AnalysisTasks.vue`（`goResults`）
- 修改：`src/app/frontend/src/api/tasks.ts`（删 `listAllResultsApi`）
- 删除：`src/app/frontend/src/views/AnalysisResult.vue`

前端无单元测试框架，以 `npm run build` 编译通过为验证；端到端由冒烟测试覆盖 API。

- [ ] **步骤 1：新建 TaskResults.vue**

新建 `src/app/frontend/src/views/TaskResults.vue`：

```vue
<template>
  <div>
    <div class="toolbar">
      <div class="button-row">
        <select v-model.number="taskId" style="width:auto" @change="onSwitch">
          <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
        <button @click="load">刷新</button>
        <button @click="back">返回分析任务</button>
      </div>
      <div class="stats"><strong>{{ runs.length }}</strong><span>个运行批次</span></div>
    </div>

    <div v-if="!runs.length" class="empty"><b>暂无分析结果</b><span>触发分析任务后将在此展示。</span></div>
    <div v-else class="item-list">
      <article v-for="run in runs" :key="run.id" class="item-card" style="flex-direction:column;align-items:stretch">
        <div class="grow" style="cursor:pointer" @click="toggleRun(run.id)">
          <div class="item-title">
            <h3>运行 #{{ run.id }}</h3>
            <span :class="['pill', run.status]">{{ run.status }}</span>
            <span class="pill">{{ modeLabel(run.mode) }}</span>
          </div>
          <div class="meta">
            <span>{{ run.created_at }}</span>
            <span v-if="run.summary">{{ run.summary }}</span>
          </div>
        </div>
        <div v-if="expandedRun === run.id" style="margin-top:8px">
          <div v-if="!resultsByRun[run.id]" class="muted" style="font-size:12px">加载中...</div>
          <div v-else-if="!resultsByRun[run.id].length" class="muted" style="font-size:12px">该批次无结果</div>
          <div v-else>
            <details v-for="r in resultsByRun[run.id]" :key="r.id" style="margin-bottom:6px">
              <summary style="cursor:pointer">
                <span :class="['pill', r.result_type === 'aggregate' ? 'warning' : 'ok']">{{ r.result_type === 'aggregate' ? '汇总' : '逐条' }}</span>
                {{ r.source_name || '未知源' }} · {{ r.created_at }}
              </summary>
              <div class="markdown" style="margin-top:6px" v-html="renderMd(r.content)"></div>
            </details>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listTasksApi, listTaskResultsApi, listRunsApi, type AnalysisTaskDetail, type AnalysisResult, type TaskRun } from '@/api/tasks'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const tasks = ref<AnalysisTaskDetail[]>([])
const taskId = ref<number>(Number(route.params.id))
const runs = ref<TaskRun[]>([])
const expandedRun = ref<number | null>(null)
const resultsByRun = reactive<Record<number, AnalysisResult[] | undefined>>({})
const renderMd = renderMarkdown

onMounted(async () => {
  tasks.value = await listTasksApi()
  if (!tasks.value.find((t) => t.id === taskId.value) && tasks.value.length) {
    taskId.value = tasks.value[0].id
  }
  await loadRuns()
})

function onSwitch() {
  router.replace({ name: 'task-results', params: { id: taskId.value } })
  loadRuns()
}

function back() {
  router.push('/analysis-tasks')
}

async function load() {
  await loadRuns()
}

async function loadRuns() {
  runs.value = await listRunsApi({ kind: 'analysis', ref_id: taskId.value, limit: 200 })
  expandedRun.value = null
}

async function toggleRun(runId: number) {
  if (expandedRun.value === runId) {
    expandedRun.value = null
    return
  }
  expandedRun.value = runId
  if (!resultsByRun[runId]) {
    resultsByRun[runId] = await listTaskResultsApi(taskId.value, runId)
  }
}

function modeLabel(m?: string | null) {
  if (m === 'full') return '全量'
  if (m === 'custom') return '自定义'
  return '增量'
}
</script>
```

- [ ] **步骤 2：修改路由**

修改 `src/app/frontend/src/router/index.ts`，删除 `analysis-result` 行，替换为带 name 的任务结果路由：

```ts
      { path: 'analysis-tasks', component: () => import('@/views/AnalysisTasks.vue'), meta: { page: 'analysis_tasks', title: '分析任务' } },
      { path: 'analysis-tasks/:id/results', name: 'task-results', component: () => import('@/views/TaskResults.vue'), meta: { page: 'analysis_tasks', title: '分析结果' } },
      { path: 'task-center', component: () => import('@/views/TaskCenter.vue'), meta: { page: 'task_center', title: '任务中心' } },
```

（即删除原 `{ path: 'analysis-result', ... }` 一行，新增 `analysis-tasks/:id/results` 一行。）

- [ ] **步骤 3：修改菜单**

修改 `src/app/frontend/src/layouts/MainLayout.vue`：
- `allMenus` 中删除 `{ path: '/analysis-result', icon: '果', page: 'analysis_result', title: '分析结果' }`。
- `pageMeta` 中删除 `analysis_result` 行。

- [ ] **步骤 4：修改 AnalysisTasks.vue 的 goResults**

修改 `src/app/frontend/src/views/AnalysisTasks.vue` 的 `goResults`：

```ts
function goResults(taskId: number) {
  router.push({ name: 'task-results', params: { id: taskId } })
}
```

- [ ] **步骤 5：清理 api/tasks.ts**

修改 `src/app/frontend/src/api/tasks.ts`，删除末尾 `listAllResultsApi` 定义。

- [ ] **步骤 6：删除旧组件**

```bash
rm src/app/frontend/src/views/AnalysisResult.vue
```

- [ ] **步骤 7：构建验证**

运行：`cd src/app/frontend && npm run build`
预期：构建成功，无 TS 错误。

- [ ] **步骤 8：Commit**

```bash
git add src/app/frontend/src/views/TaskResults.vue src/app/frontend/src/router/index.ts src/app/frontend/src/layouts/MainLayout.vue src/app/frontend/src/views/AnalysisTasks.vue src/app/frontend/src/api/tasks.ts
git rm src/app/frontend/src/views/AnalysisResult.vue
git commit -m "分析结果: 改为任务下钻详情页,按运行批次分组展示"
```

---

## 阶段 B：需求2 - 定时任务

### 任务 B1：依赖与配置

**文件：**
- 修改：`src/app/backend/requirements.txt`
- 修改：`src/config/app.json`
- 修改：`src/app/backend/core/config.py`
- 修改：`src/config/env.local.example`
- 测试：`src/tests/unit/test_config.py`

- [ ] **步骤 1：编写失败的测试**

在 `src/tests/unit/test_config.py` 末尾追加：

```python
def test_scheduler_settings():
    from app.backend.core.config import settings

    assert settings.scheduler_enabled is True
    assert settings.scheduler_misfire_grace_seconds == 300
    assert settings.scheduler_max_instances == 1
    assert settings.scheduler_coalesce is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_config.py::test_scheduler_settings -v`
预期：FAIL，`AttributeError: 'Settings' object has no attribute 'scheduler_enabled'`。

- [ ] **步骤 3：加依赖**

修改 `src/app/backend/requirements.txt`，追加一行：

```
apscheduler>=3.10
```

- [ ] **步骤 4：加 app.json 配置段**

修改 `src/config/app.json`，在 `worker` 段后追加：

```json
  "worker": {
    "max_workers": 4
  },
  "scheduler": {
    "enabled": true,
    "misfire_grace_seconds": 300,
    "max_instances": 1,
    "coalesce": true
  }
}
```

- [ ] **步骤 5：加 Settings 字段**

修改 `src/app/backend/core/config.py`，在 `__init__` 末尾（`worker_max_workers` 赋值之后、`@property raw` 之前）追加：

```python
        sch = raw.get("scheduler", {})
        self.scheduler_enabled: bool = _env("ISAS_SCHEDULER_ENABLED", sch.get("enabled", True)) in (True, "true", "True", 1, "1")
        self.scheduler_misfire_grace_seconds: int = int(
            _env("ISAS_SCHEDULER_MISFIRE_GRACE_SECONDS", sch.get("misfire_grace_seconds", 300))
        )
        self.scheduler_max_instances: int = int(
            _env("ISAS_SCHEDULER_MAX_INSTANCES", sch.get("max_instances", 1))
        )
        self.scheduler_coalesce: bool = _env("ISAS_SCHEDULER_COALESCE", sch.get("coalesce", True)) in (True, "true", "True", 1, "1")
```

- [ ] **步骤 6：env.local.example 补示例**

修改 `src/config/env.local.example`，末尾追加：

```bash
# ===== 定时任务调度器 =====
# ISAS_SCHEDULER_ENABLED=true
# ISAS_SCHEDULER_MISFIRE_GRACE_SECONDS=300
```

- [ ] **步骤 7：安装依赖并运行测试**

```bash
cd src/app/backend && pip install -r requirements.txt
cd ../.. && pytest tests/unit/test_config.py -v
```
预期：PASS。

- [ ] **步骤 8：Commit**

```bash
git add src/app/backend/requirements.txt src/config/app.json src/app/backend/core/config.py src/config/env.local.example src/tests/unit/test_config.py
git commit -m "定时任务: 新增 apscheduler 依赖与 scheduler 配置段"
```

---

### 任务 B2：模型 - ScheduledJob + TaskRun 加列 + 迁移

**文件：**
- 新建：`src/app/backend/models/scheduled_job.py`
- 修改：`src/app/backend/models/task.py`
- 修改：`src/app/backend/models/__init__.py`
- 修改：`src/app/backend/core/database.py`
- 测试：`src/tests/unit/test_scheduled_job_model.py`（新建）

- [ ] **步骤 1：编写失败的测试**

新建 `src/tests/unit/test_scheduled_job_model.py`：

```python
"""ScheduledJob model + task_runs migration tests."""
from __future__ import annotations

from sqlalchemy import inspect

from app.backend.core.database import _ensure_column, engine


def test_scheduled_job_create_and_cascade(client, admin_headers):
    # 建任务
    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []},
        headers=admin_headers,
    )
    assert t.status_code == 201
    tid = t.json()["id"]
    # 直接写一条 ScheduledJob（API 在后续任务实现，此处用 ORM）
    from app.backend.core.database import SessionLocal
    from app.backend.models.scheduled_job import ScheduledJob

    with SessionLocal() as db:
        db.add(ScheduledJob(task_id=tid, name="j1", mode="incremental", trigger_type="interval", interval_seconds=60))
        db.commit()
    # 删除任务应级联删除定时任务
    d = client.delete(f"/api/analysis-tasks/{tid}", headers=admin_headers)
    assert d.status_code == 200
    with SessionLocal() as db:
        assert db.query(ScheduledJob).count() == 0


def test_task_run_has_scheduled_job_id_column():
    cols = [c["name"] for c in inspect(engine).get_columns("task_runs")]
    assert "scheduled_job_id" in cols


def test_ensure_column_idempotent():
    _ensure_column(engine, "task_runs", "scheduled_job_id", "INTEGER")
    cols = [c["name"] for c in inspect(engine).get_columns("task_runs")]
    assert "scheduled_job_id" in cols  # 再次调用不报错


def test_ensure_column_adds_missing():
    # 在一个临时表上验证加列逻辑
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS _tmp_test (id INTEGER)")
    _ensure_column(engine, "_tmp_test", "extra", "INTEGER")
    cols = [c["name"] for c in inspect(engine).get_columns("_tmp_test")]
    assert "extra" in cols
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE _tmp_test")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_scheduled_job_model.py -v`
预期：FAIL（`ScheduledJob` 不存在；`_ensure_column` 不存在）。

- [ ] **步骤 3：新建 ScheduledJob 模型**

新建 `src/app/backend/models/scheduled_job.py`：

```python
"""Scheduled-job model: a cron/interval schedule that auto-triggers an analysis task."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.timeutil import utcnow
from .analysis import AnalysisTask


class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # full | incremental
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)  # cron | interval
    cron_expr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    task: Mapped[AnalysisTask] = relationship()
```

- [ ] **步骤 4：TaskRun 加 scheduled_job_id 列**

修改 `src/app/backend/models/task.py`，在 `TaskRun` 内 `error` 字段后追加：

```python
    scheduled_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
```

- [ ] **步骤 5：注册模型**

修改 `src/app/backend/models/__init__.py`：

```python
from .analysis import AnalysisResult, AnalysisTask, TaskSource
from .info_source import InfoItem, InfoSource
from .scheduled_job import ScheduledJob
from .task import TaskLog, TaskRun
from .user import PagePermission, User

__all__ = [
    "User",
    "PagePermission",
    "TaskRun",
    "TaskLog",
    "InfoSource",
    "InfoItem",
    "AnalysisTask",
    "TaskSource",
    "AnalysisResult",
    "ScheduledJob",
]
```

- [ ] **步骤 6：加 _ensure_column 迁移**

修改 `src/app/backend/core/database.py`，在 `init_db` 之前追加函数，并让 `init_db` 调用：

```python
from sqlalchemy import inspect, text


def _ensure_column(engine_, table_name: str, column_name: str, column_ddl: str) -> None:
    """Add a column to an existing table if missing (lightweight migration for
    tables created before the column existed). No-op for missing tables
    (create_all will build them fresh)."""
    insp = inspect(engine_)
    if not insp.has_table(table_name):
        return
    existing = {c["name"] for c in insp.get_columns(table_name)}
    if column_name not in existing:
        with engine_.begin() as conn:
            conn.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}")
            )


def init_db() -> None:
    """Create all tables. Imports models so they register on ``Base``."""
    from .. import models  # noqa: F401  (registers ORM models)

    Base.metadata.create_all(bind=engine)
    # Migrate pre-existing tables (create_all does not ALTER existing tables).
    _ensure_column(engine, "task_runs", "scheduled_job_id", "INTEGER")
```

注意：`database.py` 顶部已 `from sqlalchemy import create_engine, event`，将 `inspect, text` 并入该 import。

- [ ] **步骤 7：运行测试验证通过**

运行：`cd src && pytest tests/unit/test_scheduled_job_model.py -v`
预期：PASS。

- [ ] **步骤 8：Commit**

```bash
git add src/app/backend/models/scheduled_job.py src/app/backend/models/task.py src/app/backend/models/__init__.py src/app/backend/core/database.py src/tests/unit/test_scheduled_job_model.py
git commit -m "定时任务: 新增 ScheduledJob 模型,TaskRun 增 scheduled_job_id 列与迁移"
```

---

### 任务 B3：调度器 services/scheduler.py

**文件：**
- 新建：`src/app/backend/services/scheduler.py`
- 测试：`src/tests/unit/test_scheduler.py`（新建）

- [ ] **步骤 1：编写失败的测试**

新建 `src/tests/unit/test_scheduler.py`：

```python
"""Scheduler unit tests (no real cron waiting; _fire invoked directly)."""
from __future__ import annotations

from app.backend.core.database import SessionLocal
from app.backend.models.scheduled_job import ScheduledJob
from app.backend.models.task import TaskRun
from app.backend.services import scheduler as sched


def test_fire_creates_task_run_and_submits(client, admin_headers, sync_worker, mock_llm, monkeypatch):
    submitted = []
    monkeypatch.setattr(sched.worker, "submit", lambda fn, *a, **kw: submitted.append((fn.__name__, a)) or fn(*a, **kw))

    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []},
        headers=admin_headers,
    )
    tid = t.json()["id"]
    with SessionLocal() as db:
        job = ScheduledJob(task_id=tid, name="j", mode="incremental", trigger_type="interval", interval_seconds=60, enabled=True)
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id

    sched._fire(jid)
    with SessionLocal() as db:
        run = db.query(TaskRun).filter(TaskRun.scheduled_job_id == jid).one()
        assert run.kind == "analysis"
        assert run.ref_id == tid
        assert run.mode == "incremental"
        assert run.status == "succeeded"  # sync_worker + mock_llm 已执行
        job = db.get(ScheduledJob, jid)
        assert job.last_run_status == "succeeded"
        assert job.last_run_at is not None
    assert submitted and submitted[0][0] == "run_analysis"


def test_fire_skips_disabled_job(client, admin_headers, monkeypatch):
    submitted = []
    monkeypatch.setattr(sched.worker, "submit", lambda *a, **kw: submitted.append(1))
    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []},
        headers=admin_headers,
    )
    tid = t.json()["id"]
    with SessionLocal() as db:
        job = ScheduledJob(task_id=tid, name="j", mode="incremental", trigger_type="interval", interval_seconds=60, enabled=False)
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id
    sched._fire(jid)
    assert submitted == []


def test_start_scheduler_loads_enabled_jobs(client, admin_headers, monkeypatch):
    # start_scheduler 不应在测试里真起后台线程；mock BackgroundScheduler
    added = []
    class _FakeSched:
        def __init__(self, *a, **kw): pass
        def add_job(self, fn, trigger=None, **kw): added.append(kw.get("id"))
        def remove_job(self, jid): pass
        def start(self): pass
        def shutdown(self, **kw): pass
        def get_job(self, jid):
            class _J: next_run_time = None
            return _J()
    monkeypatch.setattr(sched, "BackgroundScheduler", _FakeSched)
    t = client.post("/api/analysis-tasks", json={"name": "t", "config": {}, "source_ids": []}, headers=admin_headers)
    tid = t.json()["id"]
    from app.backend.core.database import SessionLocal
    with SessionLocal() as db:
        db.add(ScheduledJob(task_id=tid, name="j", mode="incremental", trigger_type="interval", interval_seconds=60, enabled=True))
        db.commit()
    sched.start_scheduler()
    assert added  # enabled job 被加载
    sched.shutdown_scheduler()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_scheduler.py -v`
预期：FAIL（`scheduler` 模块不存在）。

- [ ] **步骤 3：实现 scheduler.py**

新建 `src/app/backend/services/scheduler.py`：

```python
"""Process-wide APScheduler that auto-triggers analysis tasks on schedule.

Config lives in the ``scheduled_jobs`` table (managed via API/UI). On startup
we load enabled jobs into an in-memory BackgroundScheduler; CRUD operations
sync the scheduler so DB and memory stay consistent. Firing a job creates a
``TaskRun`` and reuses the existing ``worker.submit(run_analysis, ...)`` path.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from ..core.config import settings
from ..core.database import SessionLocal
from ..core.logging import get_logger
from ..core.timeutil import utcnow
from ..models.analysis import AnalysisTask
from ..models.scheduled_job import ScheduledJob
from ..models.task import TaskRun
from . import worker
from .analysis import run_analysis

_logger = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone_display)


def _build_trigger(job: ScheduledJob):
    if job.trigger_type == "cron":
        if not job.cron_expr:
            raise ValueError("cron 模式必须填写 cron_expr")
        return CronTrigger.from_crontab(job.cron_expr, timezone=_tz())
    if job.trigger_type == "interval":
        if not job.interval_seconds or job.interval_seconds <= 0:
            raise ValueError("interval 模式必须填写大于 0 的间隔秒数")
        return IntervalTrigger(seconds=job.interval_seconds, timezone=_tz())
    raise ValueError(f"未知触发类型: {job.trigger_type}")


def _job_id(job_id: int) -> str:
    return str(job_id)


def _sync_next_run(job_id: int) -> None:
    """Persist the scheduler's next_run_time back to the DB for display."""
    if _scheduler is None:
        return
    job = _scheduler.get_job(_job_id(job_id))
    nxt: datetime | None = getattr(job, "next_run_time", None) if job else None
    with SessionLocal() as db:
        sj = db.get(ScheduledJob, job_id)
        if sj:
            sj.next_run_at = nxt
            db.commit()


def _fire(job_id: int) -> None:
    """Scheduler callback: create a TaskRun and submit run_analysis."""
    with SessionLocal() as db:
        sj = db.get(ScheduledJob, job_id)
        if sj is None or not sj.enabled:
            return
        task = db.get(AnalysisTask, sj.task_id)
        if task is None:
            _logger.warning("定时任务 %s 关联分析任务不存在", job_id)
            return
        run = TaskRun(
            kind="analysis",
            ref_id=task.id,
            ref_name=task.name,
            mode=sj.mode,
            status="pending",
            scheduled_job_id=job_id,
        )
        db.add(run)
        sj.last_run_at = utcnow()
        sj.last_run_status = "running"
        db.commit()
        db.refresh(run)
        run_id, task_id, mode = run.id, task.id, sj.mode
    worker.submit(run_analysis, run_id, task_id, mode)
    _sync_next_run(job_id)


def _add_job(sj: ScheduledJob) -> None:
    if _scheduler is None:
        return
    _scheduler.add_job(
        _fire,
        trigger=_build_trigger(sj),
        args=[sj.id],
        id=_job_id(sj.id),
        max_instances=settings.scheduler_max_instances,
        coalesce=settings.scheduler_coalesce,
        misfire_grace_time=settings.scheduler_misfire_grace_seconds,
        replace_existing=True,
    )


def add_scheduled_job(sj: ScheduledJob) -> None:
    if _scheduler is not None and sj.enabled:
        _add_job(sj)
        _sync_next_run(sj.id)


def remove_scheduled_job(job_id: int) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_job_id(job_id))
    except Exception:  # noqa: BLE001  (job may not be in scheduler if disabled)
        pass


def reschedule_scheduled_job(sj: ScheduledJob) -> None:
    remove_scheduled_job(sj.id)
    add_scheduled_job(sj)


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled:
        _logger.info("定时任务调度器已禁用 (scheduler.enabled=false)")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=_tz(),
    )
    with SessionLocal() as db:
        jobs = db.scalars(select(ScheduledJob).where(ScheduledJob.enabled.is_(True))).all()
        for sj in jobs:
            try:
                _add_job(sj)
            except Exception:  # noqa: BLE001
                _logger.exception("加载定时任务 %s 失败", sj.id)
    _scheduler.start()
    _logger.info("定时任务调度器已启动,加载 %d 个已启用任务", len(jobs))


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd src && pytest tests/unit/test_scheduler.py -v`
预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add src/app/backend/services/scheduler.py src/tests/unit/test_scheduler.py
git commit -m "定时任务: 实现 APScheduler 调度器(启停/CRUD同步/_fire复用run_analysis)"
```

---

### 任务 B4：schemas/scheduled_job.py

**文件：**
- 新建：`src/app/backend/schemas/scheduled_job.py`

- [ ] **步骤 1：新建 schema**

新建 `src/app/backend/schemas/scheduled_job.py`：

```python
"""Scheduled-job schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase


class ScheduledJobOut(ORMBase):
    id: int
    task_id: int
    name: str
    mode: str
    trigger_type: str
    cron_expr: str | None
    interval_seconds: int | None
    enabled: bool
    last_run_at: BeijingDatetime | None
    last_run_status: str | None
    next_run_at: BeijingDatetime | None
    created_at: BeijingDatetime
    updated_at: BeijingDatetime


class ScheduledJobCreate(ORMBase):
    task_id: int
    name: str
    mode: str  # full | incremental
    trigger_type: str  # cron | interval
    cron_expr: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True


class ScheduledJobUpdate(ORMBase):
    name: str | None = None
    mode: str | None = None
    trigger_type: str | None = None
    cron_expr: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None
```

- [ ] **步骤 2：Commit**

```bash
git add src/app/backend/schemas/scheduled_job.py
git commit -m "定时任务: 新增 Pydantic schemas"
```

---

### 任务 B5：API api/scheduled_jobs.py + 挂载 + lifespan 启停

**文件：**
- 新建：`src/app/backend/api/scheduled_jobs.py`
- 修改：`src/app/backend/main.py`（挂载路由 + lifespan）
- 测试：`src/tests/unit/test_scheduled_jobs_api.py`（新建）

- [ ] **步骤 1：编写失败的测试**

新建 `src/tests/unit/test_scheduled_jobs_api.py`：

```python
"""Scheduled-jobs API tests."""
from __future__ import annotations


def _make_task(client, h):
    r = client.post("/api/analysis-tasks", json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []}, headers=h)
    return r.json()["id"]


def test_create_list_update_delete(client, admin_headers):
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每天9点", "mode": "incremental", "trigger_type": "cron", "cron_expr": "0 9 * * *"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    assert r.json()["next_run_at"] is not None

    lst = client.get(f"/api/scheduled-jobs?task_id={tid}", headers=admin_headers)
    assert lst.status_code == 200 and len(lst.json()) == 1

    up = client.put(f"/api/scheduled-jobs/{jid}", json={"name": "改名"}, headers=admin_headers)
    assert up.status_code == 200 and up.json()["name"] == "改名"

    d = client.delete(f"/api/scheduled-jobs/{jid}", headers=admin_headers)
    assert d.status_code == 200


def test_invalid_cron_returns_400(client, admin_headers):
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "bad", "mode": "incremental", "trigger_type": "cron", "cron_expr": "not-a-cron"},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_toggle_and_run_now(client, admin_headers, sync_worker, mock_llm):
    tid = _make_task(client, admin_headers)
    r = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每分钟", "mode": "incremental", "trigger_type": "interval", "interval_seconds": 60},
        headers=admin_headers,
    )
    jid = r.json()["id"]

    run = client.post(f"/api/scheduled-jobs/{jid}/run", headers=admin_headers)
    assert run.status_code == 200 and "run_id" in run.json()

    tg = client.post(f"/api/scheduled-jobs/{jid}/toggle", headers=admin_headers)
    assert tg.status_code == 200 and tg.json()["enabled"] is False


def test_forbidden_for_user_without_page(client):
    # tester 是普通用户,默认无 scheduled_jobs 权限
    r = client.post("/api/auth/login", json={"username": "tester", "password": "tester123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    resp = client.get("/api/scheduled-jobs", headers=h)
    assert resp.status_code == 403
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_scheduled_jobs_api.py -v`
预期：FAIL（404，路由不存在）。

- [ ] **步骤 3：实现 API**

新建 `src/app/backend/api/scheduled_jobs.py`：

```python
"""Scheduled-job endpoints: CRUD, toggle, run-now."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..core.timeutil import utcnow
from ..models.analysis import AnalysisTask
from ..models.scheduled_job import ScheduledJob
from ..models.task import TaskRun
from ..models.user import User
from ..schemas.scheduled_job import (
    ScheduledJobCreate,
    ScheduledJobOut,
    ScheduledJobUpdate,
)
from ..services import worker
from ..services.analysis import run_analysis
from ..services import scheduler as sched_svc

router = APIRouter(prefix="/api/scheduled-jobs", tags=["定时任务"])


def _validate(req: ScheduledJobCreate | ScheduledJobUpdate, db: Session) -> None:
    if req.mode is not None and req.mode not in ("full", "incremental"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="mode 必须是 full 或 incremental")
    if req.trigger_type is not None and req.trigger_type not in ("cron", "interval"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="trigger_type 必须是 cron 或 interval")
    tt = req.trigger_type
    if tt == "cron" and not req.cron_expr:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 模式必须填写 cron_expr")
    if tt == "interval" and (not req.interval_seconds or req.interval_seconds <= 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="interval 模式必须填写大于 0 的间隔秒数")
    if tt == "cron" and req.cron_expr:
        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(req.cron_expr)
        except Exception:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 表达式不合法")


def _out(sj: ScheduledJob) -> ScheduledJobOut:
    return ScheduledJobOut.model_validate(sj)


@router.get("", response_model=list[ScheduledJobOut])
def list_jobs(
    task_id: int | None = Query(None),
    enabled: bool | None = Query(None),
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    q = select(ScheduledJob).order_by(ScheduledJob.id.desc())
    if task_id is not None:
        q = q.where(ScheduledJob.task_id == task_id)
    if enabled is not None:
        q = q.where(ScheduledJob.enabled.is_(enabled))
    return [_out(sj) for sj in db.scalars(q).all()]


@router.post("", response_model=ScheduledJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    req: ScheduledJobCreate,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    if db.get(AnalysisTask, req.task_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="分析任务不存在")
    _validate(req, db)
    sj = ScheduledJob(
        task_id=req.task_id,
        name=req.name,
        mode=req.mode,
        trigger_type=req.trigger_type,
        cron_expr=req.cron_expr,
        interval_seconds=req.interval_seconds,
        enabled=req.enabled,
    )
    db.add(sj)
    db.commit()
    db.refresh(sj)
    sched_svc.add_scheduled_job(sj)
    db.refresh(sj)
    return _out(sj)


@router.put("/{job_id}", response_model=ScheduledJobOut)
def update_job(
    job_id: int,
    req: ScheduledJobUpdate,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    _validate(req, db)
    for f in ("name", "mode", "trigger_type", "cron_expr", "interval_seconds", "enabled"):
        v = getattr(req, f)
        if v is not None:
            setattr(sj, f, v)
    db.commit()
    db.refresh(sj)
    sched_svc.reschedule_scheduled_job(sj)
    db.refresh(sj)
    return _out(sj)


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    sched_svc.remove_scheduled_job(job_id)
    db.delete(sj)
    db.commit()
    return {"detail": "已删除"}


@router.post("/{job_id}/toggle", response_model=ScheduledJobOut)
def toggle_job(
    job_id: int,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    sj.enabled = not sj.enabled
    db.commit()
    db.refresh(sj)
    if sj.enabled:
        sched_svc.add_scheduled_job(sj)
    else:
        sched_svc.remove_scheduled_job(sj.id)
    db.refresh(sj)
    return _out(sj)


@router.post("/{job_id}/run")
def run_job_now(
    job_id: int,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    task = db.get(AnalysisTask, sj.task_id)
    if task is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="关联分析任务不存在")
    run = TaskRun(
        kind="analysis",
        ref_id=task.id,
        ref_name=task.name,
        mode=sj.mode,
        status="pending",
        scheduled_job_id=sj.id,
    )
    db.add(run)
    sj.last_run_at = utcnow()
    sj.last_run_status = "running"
    db.commit()
    db.refresh(run)
    worker.submit(run_analysis, run.id, task.id, sj.mode)
    return {"run_id": run.id, "status": "pending"}
```

- [ ] **步骤 4：挂载路由 + lifespan 启停调度器**

修改 `src/app/backend/main.py`：
- 顶部 import 区追加：
  ```python
  from .api import scheduled_jobs as scheduled_jobs_api
  from .services import scheduler as sched_svc
  ```
- `lifespan` 内，在 `yield` 之前（`sync_users_from_password_file` 之后）追加 `sched_svc.start_scheduler()`；在 `yield` 之后、`worker.shutdown()` 之前追加 `sched_svc.shutdown_scheduler()`：

  ```python
      with SessionLocal() as db:
          sync_users_from_password_file(db)
      sched_svc.start_scheduler()
      yield
      sched_svc.shutdown_scheduler()
      worker.shutdown()
  ```
- 路由挂载区追加：`app.include_router(scheduled_jobs_api.router)`

- [ ] **步骤 5：运行测试验证通过**

运行：`cd src && pytest tests/unit/test_scheduled_jobs_api.py -v`
预期：PASS。

- [ ] **步骤 6：Commit**

```bash
git add src/app/backend/api/scheduled_jobs.py src/app/backend/main.py src/tests/unit/test_scheduled_jobs_api.py
git commit -m "定时任务: 新增 CRUD/启停/立即执行 API 与 lifespan 启停调度器"
```

---

### 任务 B6：engine.py 状态回写

**文件：**
- 修改：`src/app/backend/services/analysis/engine.py`
- 测试：`src/tests/unit/test_engine.py`（追加用例）

- [ ] **步骤 1：编写失败的测试**

在 `src/tests/unit/test_engine.py` 末尾追加：

```python
def test_run_analysis_writes_back_scheduled_job_status(client, admin_headers, sync_worker, mock_llm):
    from app.backend.core.database import SessionLocal
    from app.backend.models.scheduled_job import ScheduledJob
    from app.backend.models.task import TaskRun

    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []},
        headers=admin_headers,
    )
    tid = t.json()["id"]
    with SessionLocal() as db:
        sj = ScheduledJob(task_id=tid, name="j", mode="incremental", trigger_type="interval", interval_seconds=60, enabled=True)
        db.add(sj)
        db.commit()
        db.refresh(sj)
        sjid = sj.id
    # 手动创建一个带 scheduled_job_id 的 run 并执行
    from app.backend.services.analysis import run_analysis
    with SessionLocal() as db:
        run = TaskRun(kind="analysis", ref_id=tid, ref_name="t", mode="incremental", status="pending", scheduled_job_id=sjid)
        db.add(run)
        db.commit()
        db.refresh(run)
        rid = run.id
    run_analysis(rid, tid, "incremental")
    with SessionLocal() as db:
        assert db.get(ScheduledJob, sjid).last_run_status == "succeeded"


def test_run_analysis_no_writeback_for_manual_run(client, admin_headers, sync_worker, mock_llm):
    # 手动触发(scheduled_job_id=None)不应报错,也不写回
    t = client.post("/api/analysis-tasks", json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []}, headers=admin_headers)
    tid = t.json()["id"]
    r = client.post(f"/api/analysis-tasks/{tid}/run", json={"mode": "incremental"}, headers=admin_headers)
    assert r.status_code == 200
    # 不抛异常即视为通过(同步执行已完成)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd src && pytest tests/unit/test_engine.py::test_run_analysis_writes_back_scheduled_job_status -v`
预期：FAIL（`last_run_status` 仍为 `"running"` 或 NULL，未回写）。

- [ ] **步骤 3：实现状态回写**

修改 `src/app/backend/services/analysis/engine.py`：
- 顶部 import 追加：`from ..models.scheduled_job import ScheduledJob`
- 在成功分支（`run.status = "succeeded"` 之后、`db.commit()` 之前）追加回写：
  ```python
            run.status = "succeeded"
            run.finished_at = utcnow()
            run.summary = f"分析完成: 处理 {total_items} 条信息, 生成 {total_results} 条结果"
            _log(db, run_id, "INFO", run.summary)
            if run.scheduled_job_id:
                sj = db.get(ScheduledJob, run.scheduled_job_id)
                if sj:
                    sj.last_run_status = "succeeded"
            db.commit()
  ```
- 在 except 分支（`run.status = "failed"` 之后、`db.commit()` 之前）追加回写：
  ```python
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            _log(db, run_id, "ERROR", f"分析失败: {exc}")
            if run.scheduled_job_id:
                sj = db.get(ScheduledJob, run.scheduled_job_id)
                if sj:
                    sj.last_run_status = "failed"
            db.commit()
  ```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd src && pytest tests/unit/test_engine.py -v`
预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add src/app/backend/services/analysis/engine.py src/tests/unit/test_engine.py
git commit -m "分析引擎: run_analysis 结束回写 scheduled_job.last_run_status"
```

---

### 任务 B7：前端 - api/scheduledJobs.ts

**文件：**
- 新建：`src/app/frontend/src/api/scheduledJobs.ts`

- [ ] **步骤 1：新建 API 封装**

新建 `src/app/frontend/src/api/scheduledJobs.ts`：

```ts
import request from './request'

export interface ScheduledJob {
  id: number
  task_id: number
  name: string
  mode: string
  trigger_type: string
  cron_expr: string | null
  interval_seconds: number | null
  enabled: boolean
  last_run_at: string | null
  last_run_status: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export const listScheduledJobsApi = (params?: { task_id?: number; enabled?: boolean }) =>
  request.get<unknown, ScheduledJob[]>('/api/scheduled-jobs', { params })

export const createScheduledJobApi = (data: {
  task_id: number
  name: string
  mode: 'full' | 'incremental'
  trigger_type: 'cron' | 'interval'
  cron_expr?: string
  interval_seconds?: number
  enabled?: boolean
}) => request.post<unknown, ScheduledJob>('/api/scheduled-jobs', data)

export const updateScheduledJobApi = (id: number, data: Partial<{
  name: string
  mode: 'full' | 'incremental'
  trigger_type: 'cron' | 'interval'
  cron_expr?: string
  interval_seconds?: number
  enabled?: boolean
}>) => request.put<unknown, ScheduledJob>(`/api/scheduled-jobs/${id}`, data)

export const deleteScheduledJobApi = (id: number) =>
  request.delete<unknown, unknown>(`/api/scheduled-jobs/${id}`)

export const toggleScheduledJobApi = (id: number) =>
  request.post<unknown, ScheduledJob>(`/api/scheduled-jobs/${id}/toggle`)

export const runScheduledJobNowApi = (id: number) =>
  request.post<unknown, { run_id: number; status: string }>(`/api/scheduled-jobs/${id}/run`)
```

- [ ] **步骤 2：Commit**

```bash
git add src/app/frontend/src/api/scheduledJobs.ts
git commit -m "定时任务: 前端 API 封装"
```

---

### 任务 B8：前端 - ScheduledJobs.vue + 路由 + 菜单

**文件：**
- 新建：`src/app/frontend/src/views/ScheduledJobs.vue`
- 修改：`src/app/frontend/src/router/index.ts`
- 修改：`src/app/frontend/src/layouts/MainLayout.vue`
- 修改：`src/app/frontend/src/views/AnalysisTasks.vue`（可选「已配 N 个定时」）

- [ ] **步骤 1：新建 ScheduledJobs.vue**

新建 `src/app/frontend/src/views/ScheduledJobs.vue`：

```vue
<template>
  <div>
    <div class="toolbar">
      <div class="stats"><strong>{{ jobs.length }}</strong><span>个定时任务</span></div>
      <div class="button-row">
        <button @click="load">刷新</button>
        <button class="primary" @click="openCreate">＋ 新建定时任务</button>
      </div>
    </div>

    <div v-if="!jobs.length" class="empty"><b>还没有定时任务</b><span>为分析任务配置定时调度，自动触发分析。</span></div>
    <div v-else class="item-list">
      <article v-for="j in jobs" :key="j.id" class="item-card">
        <div class="file-icon">定</div>
        <div class="grow">
          <div class="item-title">
            <h3>{{ j.name }}</h3>
            <span :class="['pill', j.enabled ? 'ok' : '']">{{ j.enabled ? '启用' : '已停' }}</span>
            <span class="pill">{{ j.mode === 'full' ? '全量' : '增量' }}</span>
          </div>
          <div class="meta">
            <span>{{ taskName(j.task_id) }}</span>
            <span>{{ scheduleText(j) }}</span>
            <span>下次: {{ j.next_run_at || '-' }}</span>
            <span>上次: {{ j.last_run_at || '-' }} ({{ j.last_run_status || '-' }})</span>
          </div>
        </div>
        <div class="actions">
          <button class="accent" @click="onRunNow(j.id)">立即执行</button>
          <button @click="onToggle(j)">{{ j.enabled ? '禁用' : '启用' }}</button>
          <button @click="openEdit(j)">编辑</button>
          <button class="danger" @click="onDelete(j)">删除</button>
        </div>
      </article>
    </div>

    <div v-if="dialogVisible" class="modal" @click.self="dialogVisible = false">
      <form class="modal-card large" @submit.prevent="onSave">
        <div class="modal-head">
          <div><p class="eyebrow">SCHEDULED JOB</p><h2>{{ editing ? '编辑定时任务' : '新建定时任务' }}</h2></div>
          <button type="button" @click="dialogVisible = false">×</button>
        </div>
        <div class="form-grid">
          <label>名称<input v-model.trim="form.name" required /></label>
          <label>所属分析任务
            <select v-model.number="form.task_id" required>
              <option v-for="t in tasks" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </label>
          <label>执行模式
            <select v-model="form.mode">
              <option value="incremental">增量分析</option>
              <option value="full">全量分析</option>
            </select>
          </label>
          <label>触发类型
            <select v-model="form.trigger_type">
              <option value="cron">Cron 表达式</option>
              <option value="interval">固定间隔</option>
            </select>
          </label>
        </div>
        <label v-if="form.trigger_type === 'cron'">Cron 表达式
          <input v-model.trim="form.cron_expr" placeholder="如 0 9 * * * (每天9点)" required />
        </label>
        <div v-if="form.trigger_type === 'cron'" class="button-row" style="margin:6px 0">
          <button type="button" @click="form.cron_expr = '0 9 * * *'">每天9点</button>
          <button type="button" @click="form.cron_expr = '0 9 * * 1-5'">工作日9点</button>
          <button type="button" @click="form.cron_expr = '0 * * * *'">每小时</button>
          <button type="button" @click="form.cron_expr = '*/30 * * * *'">每30分钟</button>
        </div>
        <label v-if="form.trigger_type === 'interval'">间隔秒数
          <input v-model.number="form.interval_seconds" type="number" min="1" placeholder="如 1800 (30分钟)" required />
        </label>
        <label class="check"><input type="checkbox" v-model="form.enabled" /> 启用</label>
        <div class="modal-actions">
          <button type="button" @click="dialogVisible = false">取消</button>
          <button class="primary">保存</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { showToast } from '@/composables/toast'
import { listTasksApi, type AnalysisTaskDetail } from '@/api/tasks'
import {
  listScheduledJobsApi, createScheduledJobApi, updateScheduledJobApi,
  deleteScheduledJobApi, toggleScheduledJobApi, runScheduledJobNowApi,
  type ScheduledJob,
} from '@/api/scheduledJobs'

const jobs = ref<ScheduledJob[]>([])
const tasks = ref<AnalysisTaskDetail[]>([])
const dialogVisible = ref(false)
const editing = ref<ScheduledJob | null>(null)
const form = reactive({
  task_id: 0,
  name: '',
  mode: 'incremental' as 'full' | 'incremental',
  trigger_type: 'cron' as 'cron' | 'interval',
  cron_expr: '0 9 * * *',
  interval_seconds: 1800,
  enabled: true,
})

onMounted(async () => {
  tasks.value = await listTasksApi()
  if (tasks.value.length) form.task_id = tasks.value[0].id
  await load()
})

async function load() {
  jobs.value = await listScheduledJobsApi()
}

function taskName(tid: number) {
  return tasks.value.find((t) => t.id === tid)?.name || `#${tid}`
}

function scheduleText(j: ScheduledJob) {
  return j.trigger_type === 'cron' ? `cron: ${j.cron_expr}` : `每 ${Math.round((j.interval_seconds || 0) / 60)} 分钟`
}

function openCreate() {
  editing.value = null
  form.name = ''
  form.mode = 'incremental'
  form.trigger_type = 'cron'
  form.cron_expr = '0 9 * * *'
  form.interval_seconds = 1800
  form.enabled = true
  if (tasks.value.length) form.task_id = tasks.value[0].id
  dialogVisible.value = true
}

function openEdit(j: ScheduledJob) {
  editing.value = j
  form.task_id = j.task_id
  form.name = j.name
  form.mode = j.mode as 'full' | 'incremental'
  form.trigger_type = j.trigger_type as 'cron' | 'interval'
  form.cron_expr = j.cron_expr || '0 9 * * *'
  form.interval_seconds = j.interval_seconds || 1800
  form.enabled = j.enabled
  dialogVisible.value = true
}

async function onSave() {
  const data = {
    task_id: form.task_id,
    name: form.name,
    mode: form.mode,
    trigger_type: form.trigger_type,
    cron_expr: form.trigger_type === 'cron' ? form.cron_expr : undefined,
    interval_seconds: form.trigger_type === 'interval' ? form.interval_seconds : undefined,
    enabled: form.enabled,
  }
  try {
    if (editing.value) {
      await updateScheduledJobApi(editing.value.id, data)
    } else {
      await createScheduledJobApi(data)
    }
    showToast('保存成功')
    dialogVisible.value = false
    await load()
  } catch { /* handled */ }
}

async function onDelete(j: ScheduledJob) {
  if (!confirm(`确认删除定时任务「${j.name}」？`)) return
  await deleteScheduledJobApi(j.id)
  showToast('已删除')
  await load()
}

async function onToggle(j: ScheduledJob) {
  await toggleScheduledJobApi(j.id)
  showToast(j.enabled ? '已禁用' : '已启用')
  await load()
}

async function onRunNow(id: number) {
  const { run_id } = await runScheduledJobNowApi(id)
  showToast(`已提交执行，运行 ID: ${run_id}`)
}
</script>
```

- [ ] **步骤 2：加路由**

修改 `src/app/frontend/src/router/index.ts`，在 `analysis-tasks` 行后增加：

```ts
      { path: 'scheduled-jobs', component: () => import('@/views/ScheduledJobs.vue'), meta: { page: 'scheduled_jobs', title: '定时任务' } },
```

- [ ] **步骤 3：加菜单**

修改 `src/app/frontend/src/layouts/MainLayout.vue`：
- `allMenus` 在「分析任务」后增加：`{ path: '/scheduled-jobs', icon: '定', page: 'scheduled_jobs', title: '定时任务' },`
- `pageMeta` 增加：`scheduled_jobs: ['定时任务', '为分析任务配置定时调度，自动触发分析'],`

- [ ] **步骤 4（可选）：AnalysisTasks.vue 显示已配定时数**

修改 `src/app/frontend/src/views/AnalysisTasks.vue`，在 `onMounted` 中加载定时数并显示。此步可选，实现者可跳过；若跳过则不改该文件除 `goResults` 外的内容。

- [ ] **步骤 5：构建验证**

运行：`cd src/app/frontend && npm run build`
预期：构建成功。

- [ ] **步骤 6：Commit**

```bash
git add src/app/frontend/src/views/ScheduledJobs.vue src/app/frontend/src/router/index.ts src/app/frontend/src/layouts/MainLayout.vue src/app/frontend/src/views/AnalysisTasks.vue
git commit -m "定时任务: 新增定时任务管理页与菜单"
```

---

## 阶段 C：集成与文档

### 任务 C1：冒烟测试补充

**文件：**
- 修改：`src/tests/smoke/test_flow.py`

- [ ] **步骤 1：追加冒烟用例**

在 `src/tests/smoke/test_flow.py` 末尾追加一个测试函数（复用现有 `client`/`admin_headers`/`sync_worker`/`mock_llm` fixture）：

```python
def test_scheduled_job_flow_and_results_page_api(client, admin_headers, sync_worker, mock_llm):
    # 建源 + 任务
    src = client.post(
        "/api/info-sources",
        json={"name": "s", "type": "local_folder", "config": {"folder_path": "."}},
        headers=admin_headers,
    )
    sid = src.json()["id"]
    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": [sid]},
        headers=admin_headers,
    )
    tid = t.json()["id"]

    # 建定时任务(间隔)并立即执行
    sj = client.post(
        "/api/scheduled-jobs",
        json={"task_id": tid, "name": "每分钟", "mode": "incremental", "trigger_type": "interval", "interval_seconds": 60},
        headers=admin_headers,
    )
    assert sj.status_code == 201
    jid = sj.json()["id"]

    run = client.post(f"/api/scheduled-jobs/{jid}/run", headers=admin_headers)
    assert run.status_code == 200
    rid = run.json()["run_id"]

    # 任务中心能按 ref_id 查到该 run
    runs = client.get(f"/api/task-center/runs?kind=analysis&ref_id={tid}", headers=admin_headers)
    assert any(r["id"] == rid for r in runs.json())

    # 结果详情页 API: 按任务取结果、按 run 取结果
    res = client.get(f"/api/analysis-tasks/{tid}/results?run_id={rid}", headers=admin_headers)
    assert res.status_code == 200

    # 全局结果端点已删除
    gone = client.get("/api/analysis-results", headers=admin_headers)
    assert gone.status_code == 404

    # 清理: 禁用并删除定时任务
    assert client.post(f"/api/scheduled-jobs/{jid}/toggle", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/scheduled-jobs/{jid}", headers=admin_headers).status_code == 200
```

- [ ] **步骤 2：运行全部测试**

运行：`cd src && pytest -v`
预期：全部 PASS。

- [ ] **步骤 3：Commit**

```bash
git add src/tests/smoke/test_flow.py
git commit -m "测试: 补充定时任务与结果详情页冒烟用例"
```

---

### 任务 C2：文档更新

**文件：**
- 修改：`src/README.md`
- 修改：`src/docs/需求规格说明书.md`
- 修改：`src/docs/设计说明书.md`

- [ ] **步骤 1：更新 README.md**

在 `src/README.md` 的页面介绍表中：删除「分析结果」行，新增「定时任务」行；在配置文件说明中增加 `scheduler` 段说明；在接口列表中增加 `/api/scheduled-jobs` 并标注 `/api/analysis-results` 已移除。

- [ ] **步骤 2：更新需求规格说明书.md**

在 `src/docs/需求规格说明书.md`：
- 3.3 节 FR-TASK-6「分析结果持久化，可按任务/运行查看」补充：通过分析任务「结果」下钻进入任务结果详情页查看。
- 新增 3.6 节「定时任务」：
  - FR-SCH-1：可为分析任务配置定时任务，支持 cron 表达式与固定间隔两种触发方式。
  - FR-SCH-2：一个分析任务可配置多个定时任务；每个定时任务可选择增量/全量模式。
  - FR-SCH-3：定时任务支持启用/禁用、立即执行、编辑、删除。
  - FR-SCH-4：定时触发的执行记录在任务中心查看。
- 3.1 节页面权限键列表更新：删除 `analysis_result`，新增 `scheduled_jobs`。

- [ ] **步骤 3：更新设计说明书.md**

在 `src/docs/设计说明书.md`：
- 第 4 节数据库表追加 `scheduled_jobs` 表与 `task_runs.scheduled_job_id` 列。
- 第 5 节新增 5.5「定时任务调度器（services/scheduler.py）」：APScheduler BackgroundScheduler、时区 `Asia/Shanghai`、`_fire` 复用 `run_analysis`、CRUD 同步、misfire/max_instances 配置。
- 第 6 节 API 表：删除 `GET /api/analysis-results`；新增 `/api/scheduled-jobs` 系列；`task-center/runs` 标注支持 `ref_id`。
- 5.1 节页面权限键更新：删 `analysis_result`、增 `scheduled_jobs`。

- [ ] **步骤 4：Commit**

```bash
git add src/README.md src/docs/需求规格说明书.md src/docs/设计说明书.md
git commit -m "文档: 同步分析结果页改造与定时任务功能"
```

---

## 自检

**1. 规格覆盖度：**
- 需求1 删除独立分析结果页 -> A2（后端删端点/权限键）+ A3（前端删页/路由/菜单 + 新建 TaskResults.vue）。✓
- 需求1 下钻详情页（按批次分组+折叠 Markdown）-> A1（ref_id 过滤）+ A3（TaskResults.vue）。✓
- 需求2 数据模型 scheduled_jobs + TaskRun.scheduled_job_id -> B2。✓
- 需求2 调度器（APScheduler、时区、_fire 复用、CRUD 同步、misfire/max_instances）-> B3。✓
- 需求2 API（CRUD/启停/立即执行/权限/cron 校验）-> B5。✓
- 需求2 状态回写 -> B6。✓
- 需求2 前端页面 + 菜单 + 路由 -> B7（API）+ B8（页面/路由/菜单）。✓
- 横切：pages.py 删 analysis_result 增 scheduled_jobs -> A2（删）+ B5 测试隐含 scheduled_jobs 权限键已在 A2 加入（A2 步骤3 已加 scheduled_jobs）。✓
- 配置 app.json scheduler 段 + config.py 字段 + env.local 示例 -> B1。✓
- 依赖 apscheduler -> B1。✓
- 迁移 task_runs 加列 -> B2（_ensure_column）。✓
- 测试（单元+冒烟）-> 各任务 TDD + C1。✓
- 文档 -> C2。✓

**2. 占位符扫描：** 无 TODO/待定；每个代码步骤含实际代码；前端任务以 `npm run build` 为验证（项目无前端测试框架，属合理）。B8 步骤4「可选」明确标注可跳过且不影响主流程。✓

**3. 类型一致性：**
- `ScheduledJob` 字段在 B2（模型）、B4（schema）、B7（TS interface）三处一致：`task_id/name/mode/trigger_type/cron_expr/interval_seconds/enabled/last_run_at/last_run_status/next_run_at/created_at/updated_at`。✓
- `TaskRun.scheduled_job_id` 在 B2（模型加列）、B3（_fire 写入）、B5（run_job_now 写入）、B6（回写）一致。✓
- `_fire(job_id)` 签名在 B3 实现与测试一致。✓
- `add_scheduled_job/remove_scheduled_job/reschedule_scheduled_job` 在 B3 定义、B5 调用一致。✓
- 前端 `listScheduledJobsApi` 等在 B7 定义、B8 调用一致。✓
- 路由 name `task-results` 在 A3 路由定义与 `goResults` 跳转一致。✓

**4. 已知约束（非缺陷）：**
- 测试 fixture 用 `drop_all+create_all` 重建表，`scheduled_job_id` 列在测试中天然存在；生产增量升级靠 `_ensure_column` 迁移，由 `test_ensure_column_adds_missing` 单独覆盖。✓
- APScheduler 单进程运行；多 worker 部署需改 jobstore（设计规格第 8 节已记录为已知约束）。✓
