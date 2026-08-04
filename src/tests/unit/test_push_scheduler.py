"""Push scheduler integration tests: cron/interval registration, start/load, no-scheduler noop."""
from __future__ import annotations

from app.backend.core.database import SessionLocal
from app.backend.models.push import PushRule
from app.backend.services.push import push_scheduler as push_sched


class _FakeSched:
    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def add_job(self, fn, trigger=None, **kw):
        self.jobs[kw.get("id")] = kw

    def remove_job(self, jid):
        self.jobs.pop(jid, None)

    def get_job(self, jid):
        return None


def _patch_sched(monkeypatch, fake):
    monkeypatch.setattr(push_sched.sched_svc, "get_scheduler", lambda: fake)


def test_add_push_job_registers_cron(client, monkeypatch):
    fake = _FakeSched()
    _patch_sched(monkeypatch, fake)
    rule = PushRule(
        id=5,
        name="r",
        trigger_mode="scheduled",
        enabled=True,
        cron_expr="*/5 * * * *",
        task_id=None,
        event_types=["per_item"],
        recipients=["a@x.com"],
    )
    push_sched.add_push_job(rule)
    assert "push-5" in fake.jobs


def test_add_push_job_skips_non_scheduled(client, monkeypatch):
    fake = _FakeSched()
    _patch_sched(monkeypatch, fake)
    rule = PushRule(
        id=6,
        name="r",
        trigger_mode="manual",
        enabled=True,
        task_id=None,
        event_types=["per_item"],
        recipients=["a@x.com"],
    )
    push_sched.add_push_job(rule)
    assert fake.jobs == {}


def test_remove_push_job(client, monkeypatch):
    fake = _FakeSched()
    _patch_sched(monkeypatch, fake)
    fake.jobs["push-7"] = {}
    push_sched.remove_push_job(7)
    assert "push-7" not in fake.jobs


def test_reschedule_push_job(client, monkeypatch):
    fake = _FakeSched()
    _patch_sched(monkeypatch, fake)
    rule = PushRule(
        id=9,
        name="r",
        trigger_mode="scheduled",
        enabled=True,
        interval_seconds=120,
        task_id=None,
        event_types=["per_item"],
        recipients=["a@x.com"],
    )
    push_sched.reschedule_push_job(rule)
    assert "push-9" in fake.jobs


def test_start_push_scheduler_loads_only_enabled_scheduled(client, monkeypatch):
    fake = _FakeSched()
    _patch_sched(monkeypatch, fake)
    with SessionLocal() as db:
        db.add(PushRule(name="on", trigger_mode="scheduled", enabled=True, cron_expr="* * * * *", task_id=None, event_types=["per_item"], recipients=["a@x.com"]))
        db.add(PushRule(name="off", trigger_mode="scheduled", enabled=False, cron_expr="* * * * *", task_id=None, event_types=["per_item"], recipients=["a@x.com"]))
        db.add(PushRule(name="manual", trigger_mode="manual", enabled=True, task_id=None, event_types=["per_item"], recipients=["a@x.com"]))
        db.commit()
    push_sched.start_push_scheduler()
    assert len(fake.jobs) == 1  # 只加载 enabled & scheduled


def test_start_push_scheduler_no_scheduler_is_noop(client, monkeypatch):
    monkeypatch.setattr(push_sched.sched_svc, "get_scheduler", lambda: None)
    with SessionLocal() as db:
        db.add(PushRule(name="on", trigger_mode="scheduled", enabled=True, cron_expr="* * * * *", task_id=None, event_types=["per_item"], recipients=["a@x.com"]))
        db.commit()
    push_sched.start_push_scheduler()  # 不抛异常
