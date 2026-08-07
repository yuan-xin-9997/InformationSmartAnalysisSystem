"""Push runs API tests: list (has_preview / attachment_summary) + preview endpoint.

push-email-preview-inline-figures.
"""
from __future__ import annotations

from app.backend.core.database import SessionLocal
from app.backend.models.analysis import AnalysisTask
from app.backend.models.push import PushRule, PushRun


def _setup_task_rule(db) -> tuple[int, int]:
    task = AnalysisTask(name="T", config={})
    db.add(task)
    db.commit()
    db.refresh(task)
    rule = PushRule(
        name="r",
        task_id=task.id,
        event_types=["per_item"],
        recipients=["a@x.com"],
        trigger_mode="manual",
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return task.id, rule.id


def _login(client, username: str, password: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_preview_success(client, admin_headers):
    with SessionLocal() as db:
        tid, rid = _setup_task_rule(db)
        run = PushRun(
            rule_id=rid,
            trigger_mode="manual",
            recipients=["a@x.com"],
            event_count=2,
            status="succeeded",
            subject="【信息分析】r - 2条新事件",
            email_html='<div><img src="data:image/png;base64,AAAA" /></div>',
            attachment_summary=[{"filename": "f0.png", "kind": "figure"}],
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    r = client.get(
        f"/api/analysis-tasks/{tid}/push/runs/{run_id}/preview",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject"] == "【信息分析】r - 2条新事件"
    assert "data:image/png;base64,AAAA" in body["html"]
    assert body["attachments"] == [{"filename": "f0.png", "kind": "figure"}]


def test_preview_404_when_no_content(client, admin_headers):
    """no_new 记录无 email_html -> 404。"""
    with SessionLocal() as db:
        tid, rid = _setup_task_rule(db)
        run = PushRun(
            rule_id=rid, trigger_mode="manual", recipients=["a@x.com"],
            event_count=0, status="no_new",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    r = client.get(
        f"/api/analysis-tasks/{tid}/push/runs/{run_id}/preview",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert "无可预览内容" in r.json()["detail"]


def test_preview_404_when_run_not_in_task(client, admin_headers):
    """run 归属另一任务 -> 404。"""
    with SessionLocal() as db:
        tid_a, rid_a = _setup_task_rule(db)
        run = PushRun(
            rule_id=rid_a, trigger_mode="manual", recipients=["a@x.com"],
            event_count=1, status="succeeded", email_html="<div>a</div>",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
        # 创建任务 B
        task_b = AnalysisTask(name="B", config={})
        db.add(task_b)
        db.commit()
        tid_b = task_b.id
    r = client.get(
        f"/api/analysis-tasks/{tid_b}/push/runs/{run_id}/preview",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_preview_401_without_auth(client):
    with SessionLocal() as db:
        tid, rid = _setup_task_rule(db)
        run = PushRun(
            rule_id=rid, trigger_mode="manual", recipients=["a@x.com"],
            event_count=1, status="succeeded", email_html="<div>a</div>",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    r = client.get(f"/api/analysis-tasks/{tid}/push/runs/{run_id}/preview")
    assert r.status_code == 401


def test_preview_403_without_analysis_tasks_perm(client):
    """tester（普通用户，无 analysis_tasks 权限）-> 403。"""
    with SessionLocal() as db:
        tid, rid = _setup_task_rule(db)
        run = PushRun(
            rule_id=rid, trigger_mode="manual", recipients=["a@x.com"],
            event_count=1, status="succeeded", email_html="<div>a</div>",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
    token = _login(client, "tester", "tester123")
    r = client.get(
        f"/api/analysis-tasks/{tid}/push/runs/{run_id}/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_list_push_runs_exposes_has_preview_and_attachment_summary(client, admin_headers):
    with SessionLocal() as db:
        tid, rid = _setup_task_rule(db)
        # 1) 有预览
        db.add(PushRun(
            rule_id=rid, trigger_mode="manual", recipients=["a@x.com"],
            event_count=2, status="succeeded",
            subject="S", email_html="<div>x</div>",
            attachment_summary=[{"filename": "f.png", "kind": "figure"}],
        ))
        # 2) 无预览（no_new）
        db.add(PushRun(
            rule_id=rid, trigger_mode="manual", recipients=["a@x.com"],
            event_count=0, status="no_new",
        ))
        db.commit()
    r = client.get(f"/api/analysis-tasks/{tid}/push/runs", headers=admin_headers)
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 2
    # 倒序按 id.desc()：先插入的 succeeded(id 小) 在后，no_new(id 大) 在前
    assert runs[0]["has_preview"] is False
    assert runs[0]["subject"] is None
    assert runs[0]["attachment_summary"] is None
    assert runs[1]["has_preview"] is True
    assert runs[1]["subject"] == "S"
    assert runs[1]["attachment_summary"] == [{"filename": "f.png", "kind": "figure"}]
