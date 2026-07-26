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
        assert job.last_run_status == "succeeded"  # 定时触发链路终态由 engine.py 回写
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
    # client fixture 可能已启动真调度器(B5 后),先重置 _scheduler 才能测试 start_scheduler 加载逻辑
    sched.shutdown_scheduler()
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
