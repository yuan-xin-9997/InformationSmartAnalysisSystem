"""Consolidated task sub-config API tests (consolidate-task-analysis-page).

Covers the 1:1 schedule & push configs managed through ``/api/analysis-tasks``:
upsert (no duplicate), delete via ``null``, validation, run-now / manual-trigger,
push history, permission (403), SMTP config, and the schedule ``next_run_at``
Beijing-time correctness.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.backend.core.database import SessionLocal
from app.backend.models.push import PushRule, PushRun
from app.backend.models.scheduled_job import ScheduledJob


# ---------- helpers ----------


def _make_task(client, h, **over):
    body = {"name": "t", "config": {"mode": "per_item"}, "source_ids": []}
    body.update(over)
    r = client.post("/api/analysis-tasks", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _patch_sched(monkeypatch):
    """No-op the scheduler sync for schedule CRUD tests (avoid real job registration)."""
    from app.backend.services import scheduler as sched_svc

    monkeypatch.setattr(sched_svc, "add_scheduled_job", lambda sj: None)
    monkeypatch.setattr(sched_svc, "reschedule_scheduled_job", lambda sj: None)
    monkeypatch.setattr(sched_svc, "remove_scheduled_job", lambda jid: None)


def _patch_push_sched(monkeypatch):
    from app.backend.api import analysis_tasks as api

    monkeypatch.setattr(api, "reschedule_push_job", lambda rule: None)
    monkeypatch.setattr(api, "remove_push_job", lambda rid: None)


def _tester_headers(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "tester", "password": "tester123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _schedule_body(**over):
    body = {"enabled": True, "mode": "incremental", "trigger_type": "cron", "cron_expr": "0 9 * * *"}
    body.update(over)
    return body


def _push_body(**over):
    body = {
        "enabled": True,
        "event_types": ["per_item"],
        "recipients": ["a@x.com"],
        "trigger_mode": "manual",
    }
    body.update(over)
    return body


# ---------- schedule (1:1) ----------


def test_create_task_with_schedule(client, admin_headers, monkeypatch):
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers, schedule=_schedule_body())
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["schedule"] is not None
    assert detail["schedule"]["cron_expr"] == "0 9 * * *"
    with SessionLocal() as db:
        assert db.query(ScheduledJob).filter(ScheduledJob.task_id == tid).count() == 1


def test_upsert_schedule_updates_not_duplicates(client, admin_headers, monkeypatch):
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers, schedule=_schedule_body())
    # second save -> update, not a second row
    client.put(
        f"/api/analysis-tasks/{tid}",
        json={"schedule": _schedule_body(cron_expr="0 10 * * *")},
        headers=admin_headers,
    )
    with SessionLocal() as db:
        assert db.query(ScheduledJob).filter(ScheduledJob.task_id == tid).count() == 1
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["schedule"]["cron_expr"] == "0 10 * * *"


def test_delete_schedule_via_null(client, admin_headers, monkeypatch):
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers, schedule=_schedule_body())
    client.put(f"/api/analysis-tasks/{tid}", json={"schedule": None}, headers=admin_headers)
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["schedule"] is None
    with SessionLocal() as db:
        assert db.query(ScheduledJob).filter(ScheduledJob.task_id == tid).count() == 0


def test_schedule_absent_leaves_untouched(client, admin_headers, monkeypatch):
    """PUT without the schedule field must not delete the existing schedule."""
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers, schedule=_schedule_body())
    client.put(f"/api/analysis-tasks/{tid}", json={"name": "改名"}, headers=admin_headers)
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["name"] == "改名"
    assert detail["schedule"] is not None  # untouched


def test_invalid_cron_returns_400(client, admin_headers, monkeypatch):
    _patch_sched(monkeypatch)
    r = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": [],
              "schedule": _schedule_body(cron_expr="not-a-cron")},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_schedule_run_now(client, admin_headers, monkeypatch, sync_worker, mock_llm):
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers, schedule=_schedule_body(trigger_type="interval", interval_seconds=60, cron_expr=None))
    r = client.post(f"/api/analysis-tasks/{tid}/schedule/run", headers=admin_headers)
    assert r.status_code == 200
    assert "run_id" in r.json()


def test_schedule_run_now_without_config_400(client, admin_headers, monkeypatch):
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers)
    r = client.post(f"/api/analysis-tasks/{tid}/schedule/run", headers=admin_headers)
    assert r.status_code == 400


def test_schedule_trigger_type_switch_clears_opposite(client, admin_headers, monkeypatch):
    _patch_sched(monkeypatch)
    tid = _make_task(client, admin_headers, schedule=_schedule_body(trigger_type="interval", interval_seconds=60, cron_expr=None))
    # switch to cron -> interval_seconds cleared
    up = client.put(
        f"/api/analysis-tasks/{tid}",
        json={"schedule": _schedule_body(trigger_type="cron", cron_expr="0 9 * * *")},
        headers=admin_headers,
    )
    assert up.status_code == 200, up.text
    sched = up.json()["schedule"]
    assert sched["trigger_type"] == "cron"
    assert sched["cron_expr"] == "0 9 * * *"
    assert sched["interval_seconds"] is None


def test_schedule_next_run_at_is_beijing_time(client, admin_headers, mock_llm):
    """next_run_at must be correct Beijing time (no +8h normalization bug)."""
    tid = _make_task(client, admin_headers, schedule=_schedule_body(trigger_type="interval", interval_seconds=60, cron_expr=None))
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    next_run_at_str = detail["schedule"]["next_run_at"]
    assert next_run_at_str is not None
    BJ = ZoneInfo("Asia/Shanghai")
    next_run_at = datetime.fromisoformat(next_run_at_str)
    assert next_run_at.tzinfo is not None
    delta = (next_run_at - datetime.now(BJ)).total_seconds()
    assert 0 < delta < 600, f"next_run_at {next_run_at} 偏离 now 达 {delta}s,疑似 +8h bug"


def test_schedule_forbidden_for_user(client):
    h = _tester_headers(client)
    # tester has no analysis_tasks permission
    r = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "source_ids": [], "schedule": _schedule_body()},
        headers=h,
    )
    assert r.status_code == 403


# ---------- push (1:1) ----------


def test_create_task_with_push(client, admin_headers, monkeypatch):
    _patch_push_sched(monkeypatch)
    tid = _make_task(client, admin_headers, push=_push_body())
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["push"] is not None
    assert detail["push"]["trigger_mode"] == "manual"
    with SessionLocal() as db:
        assert db.query(PushRule).filter(PushRule.task_id == tid).count() == 1


def test_upsert_push_updates_not_duplicates(client, admin_headers, monkeypatch):
    _patch_push_sched(monkeypatch)
    tid = _make_task(client, admin_headers, push=_push_body())
    client.put(
        f"/api/analysis-tasks/{tid}",
        json={"push": _push_body(recipients=["b@x.com"])},
        headers=admin_headers,
    )
    with SessionLocal() as db:
        assert db.query(PushRule).filter(PushRule.task_id == tid).count() == 1
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["push"]["recipients"] == ["b@x.com"]


def test_delete_push_via_null(client, admin_headers, monkeypatch):
    _patch_push_sched(monkeypatch)
    tid = _make_task(client, admin_headers, push=_push_body())
    client.put(f"/api/analysis-tasks/{tid}", json={"push": None}, headers=admin_headers)
    detail = client.get(f"/api/analysis-tasks/{tid}", headers=admin_headers).json()
    assert detail["push"] is None
    with SessionLocal() as db:
        assert db.query(PushRule).filter(PushRule.task_id == tid).count() == 0


def test_scheduled_push_requires_schedule(client, admin_headers, monkeypatch):
    _patch_push_sched(monkeypatch)
    r = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "source_ids": [], "push": _push_body(trigger_mode="scheduled")},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_push_trigger_and_history(client, admin_headers, monkeypatch, sync_worker, mock_llm):
    """手动触发推送 -> 历史记录正确（mock 邮件发送）。"""
    import pathlib
    import tempfile

    from app.backend.services.push.channels import email_channel

    sent: list = []
    monkeypatch.setattr(
        email_channel.EmailChannel,
        "send",
        lambda self, cfg, recipients, subject, html, text, attachments=None, inline_images=None: sent.append(list(recipients)),
    )
    _patch_push_sched(monkeypatch)

    d = pathlib.Path(tempfile.mkdtemp())
    (d / "a.txt").write_text("关键事件A", encoding="utf-8")
    sid = client.post(
        "/api/info-sources",
        headers=admin_headers,
        json={"name": "s", "type": "local_folder", "config": {"folder_path": str(d), "patterns": ["*.txt"]}},
    ).json()["id"]
    client.post(f"/api/info-sources/{sid}/sync", headers=admin_headers)
    tid = client.post(
        "/api/analysis-tasks",
        headers=admin_headers,
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": [sid]},
    ).json()["id"]
    client.post(f"/api/analysis-tasks/{tid}/run", headers=admin_headers, json={"mode": "incremental"})

    # SMTP + push config
    client.put("/api/push/smtp", headers=admin_headers,
               json={"host": "smtp.x.com", "port": 587, "from_email": "n@x.com", "password": "pw"})
    client.put(
        f"/api/analysis-tasks/{tid}",
        headers=admin_headers,
        json={"push": _push_body(recipients=["to@x.com"])},
    )

    trig = client.post(f"/api/analysis-tasks/{tid}/push/trigger", headers=admin_headers)
    assert trig.status_code == 200
    assert trig.json()["ok"] is True

    runs = client.get(f"/api/analysis-tasks/{tid}/push/runs", headers=admin_headers).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["event_count"] == 1
    assert sent and sent[0] == ["to@x.com"]


def test_push_runs_history_empty_without_config(client, admin_headers, monkeypatch):
    _patch_push_sched(monkeypatch)
    tid = _make_task(client, admin_headers)
    runs = client.get(f"/api/analysis-tasks/{tid}/push/runs", headers=admin_headers).json()
    assert runs == []


def test_push_trigger_without_config_400(client, admin_headers, monkeypatch):
    _patch_push_sched(monkeypatch)
    tid = _make_task(client, admin_headers)
    r = client.post(f"/api/analysis-tasks/{tid}/push/trigger", headers=admin_headers)
    assert r.status_code == 400


def test_push_forbidden_for_user(client):
    h = _tester_headers(client)
    r = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "source_ids": [], "push": _push_body()},
        headers=h,
    )
    assert r.status_code == 403


# ---------- SMTP ----------


def test_smtp_get_put(client, admin_headers):
    r = client.put(
        "/api/push/smtp",
        headers=admin_headers,
        json={"host": "smtp.x.com", "port": 587, "from_email": "n@x.com", "password": "pw"},
    )
    assert r.status_code == 200
    cfg = client.get("/api/push/smtp", headers=admin_headers).json()
    assert cfg["host"] == "smtp.x.com"
    assert cfg["password"] != "pw"  # masked


def test_smtp_forbidden_for_user(client):
    h = _tester_headers(client)
    assert client.get("/api/push/smtp", headers=h).status_code == 403
