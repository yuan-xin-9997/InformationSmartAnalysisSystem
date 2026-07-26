"""Push rule API tests: CRUD, scheduled validation, manual trigger, history, permission."""
from __future__ import annotations

from app.backend.core.database import SessionLocal
from app.backend.models.push import PushRule, PushRun


def _no_sched(monkeypatch):
    """Avoid touching the real scheduler in CRUD tests."""
    from app.backend.api import push as push_api

    monkeypatch.setattr(push_api, "add_push_job", lambda rule: None)
    monkeypatch.setattr(push_api, "reschedule_push_job", lambda rule: None)
    monkeypatch.setattr(push_api, "remove_push_job", lambda rid: None)


def _create_rule(client, headers, **over):
    body = {
        "name": "r",
        "task_ids": [1],
        "event_types": ["per_item"],
        "recipients": ["a@x.com"],
        "trigger_mode": "manual",
    }
    body.update(over)
    return client.post("/api/push/rules", json=body, headers=headers)


def _tester_headers(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "tester", "password": "tester123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_create_and_list_rule(client, admin_headers, monkeypatch):
    _no_sched(monkeypatch)
    r = _create_rule(client, admin_headers)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["trigger_mode"] == "manual"
    assert r.json()["channel"] == "email"
    lst = client.get("/api/push/rules", headers=admin_headers).json()
    assert any(x["id"] == rid for x in lst)


def test_create_scheduled_requires_schedule(client, admin_headers, monkeypatch):
    _no_sched(monkeypatch)
    r = _create_rule(client, admin_headers, trigger_mode="scheduled")  # 无 cron/interval
    assert r.status_code == 400


def test_create_scheduled_with_cron_ok(client, admin_headers, monkeypatch):
    added = []
    from app.backend.api import push as push_api

    monkeypatch.setattr(push_api, "add_push_job", lambda rule: added.append(rule.id))
    monkeypatch.setattr(push_api, "reschedule_push_job", lambda rule: None)
    monkeypatch.setattr(push_api, "remove_push_job", lambda rid: None)
    r = _create_rule(client, admin_headers, trigger_mode="scheduled", cron_expr="0 0 1 1 *")
    assert r.status_code == 201, r.text
    assert added == [r.json()["id"]]  # 创建后注册到调度器


def test_update_rule(client, admin_headers, monkeypatch):
    _no_sched(monkeypatch)
    rid = _create_rule(client, admin_headers).json()["id"]
    r = client.put(
        f"/api/push/rules/{rid}",
        json={"name": "r2", "enabled": False},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "r2"
    assert r.json()["enabled"] is False


def test_update_rule_calls_reschedule(client, admin_headers, monkeypatch):
    rescheduled = []
    from app.backend.api import push as push_api

    monkeypatch.setattr(push_api, "add_push_job", lambda rule: None)
    monkeypatch.setattr(push_api, "reschedule_push_job", lambda rule: rescheduled.append(rule.id))
    monkeypatch.setattr(push_api, "remove_push_job", lambda rid: None)
    rid = _create_rule(client, admin_headers).json()["id"]
    client.put(f"/api/push/rules/{rid}", json={"enabled": False}, headers=admin_headers)
    assert rescheduled == [rid]


def test_delete_rule(client, admin_headers, monkeypatch):
    _no_sched(monkeypatch)
    rid = _create_rule(client, admin_headers).json()["id"]
    d = client.delete(f"/api/push/rules/{rid}", headers=admin_headers)
    assert d.status_code == 200
    with SessionLocal() as db:
        assert db.get(PushRule, rid) is None


def test_manual_trigger_submits_worker(client, admin_headers, monkeypatch):
    _no_sched(monkeypatch)
    rid = _create_rule(client, admin_headers).json()["id"]
    submitted = []
    from app.backend.api import push as push_api

    monkeypatch.setattr(push_api.worker, "submit", lambda fn, *a, **kw: submitted.append(a))
    r = client.post(f"/api/push/rules/{rid}/trigger", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert submitted == [(rid, "manual")]


def test_list_runs_history(client, admin_headers, monkeypatch):
    _no_sched(monkeypatch)
    rid = _create_rule(client, admin_headers).json()["id"]
    with SessionLocal() as db:
        db.add(
            PushRun(
                rule_id=rid,
                trigger_mode="manual",
                recipients=["a@x.com"],
                event_count=2,
                status="succeeded",
            )
        )
        db.commit()
    runs = client.get(f"/api/push/rules/{rid}/runs", headers=admin_headers).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["event_count"] == 2
    assert runs[0]["recipients"] == ["a@x.com"]


def test_rule_endpoints_require_permission(client):
    h = _tester_headers(client)
    assert client.get("/api/push/rules", headers=h).status_code == 403
    assert client.post("/api/push/rules", json={"name": "x", "trigger_mode": "manual"}, headers=h).status_code == 403
