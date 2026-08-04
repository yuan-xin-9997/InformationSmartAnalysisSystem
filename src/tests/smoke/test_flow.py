"""End-to-end smoke test of the full API flow."""
from __future__ import annotations

import pathlib
import tempfile


def test_full_flow(client, admin_headers, sync_worker, mock_llm):
    # health
    assert client.get("/api/health").json() == {"status": "ok"}

    # wrong password rejected
    r = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401

    # current user + config masking
    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert me["user"]["username"] == "admin"
    cfg = client.get("/api/config", headers=admin_headers).json()
    assert "******" in cfg["config"]["auth"]["secret_key"]

    # info-source create + types + invalid config
    assert len(client.get("/api/info-sources/types", headers=admin_headers).json()) == 3
    bad = client.post(
        "/api/info-sources",
        headers=admin_headers,
        json={"name": "bad", "type": "local_folder", "config": {}},
    )
    assert bad.status_code == 400

    d = pathlib.Path(tempfile.mkdtemp())
    (d / "a.txt").write_text("文章内容A", encoding="utf-8")
    (d / "b.txt").write_text("文章内容B", encoding="utf-8")
    sid = client.post(
        "/api/info-sources",
        headers=admin_headers,
        json={
            "name": "本地源",
            "type": "local_folder",
            "config": {"folder_path": str(d), "patterns": ["*.txt"]},
        },
    ).json()["id"]

    # check + sync
    check = client.post(f"/api/info-sources/{sid}/check", headers=admin_headers).json()
    assert check["status"] == "ok"
    client.post(f"/api/info-sources/{sid}/sync", headers=admin_headers)
    items = client.get(f"/api/info-sources/{sid}/items", headers=admin_headers).json()
    assert len(items) == 2

    # analysis task -> run -> results
    tid = client.post(
        "/api/analysis-tasks",
        headers=admin_headers,
        json={"name": "分析1", "config": {"mode": "per_item"}, "source_ids": [sid]},
    ).json()["id"]
    run = client.post(
        f"/api/analysis-tasks/{tid}/run", headers=admin_headers, json={"mode": "incremental"}
    ).json()
    run_detail = client.get(
        f"/api/task-center/runs/{run['run_id']}", headers=admin_headers
    ).json()
    assert run_detail["status"] == "succeeded"
    results = client.get(
        f"/api/analysis-tasks/{tid}/results", headers=admin_headers
    ).json()
    assert len(results) == 2

    # task-center lists runs and logs
    runs = client.get("/api/task-center/runs", headers=admin_headers).json()
    assert len(runs) >= 1
    assert run_detail["logs"], "run should have logs"

    # permission management: grant tester info_sources, verify access
    users = client.get("/api/users", headers=admin_headers).json()
    tester = next(u for u in users if u["username"] == "tester")
    client.put(
        f"/api/users/{tester['id']}/permissions",
        headers=admin_headers,
        json={"page_keys": ["info_sources"]},
    )

    tester_token = client.post(
        "/api/auth/login", json={"username": "tester", "password": "tester123"}
    ).json()["access_token"]
    th = {"Authorization": f"Bearer {tester_token}"}
    # tester can now list sources
    assert client.get("/api/info-sources", headers=th).status_code == 200
    # tester still cannot manage users (admin only)
    assert client.get("/api/users", headers=th).status_code == 403
    # tester cannot access system-config (not granted)
    assert client.get("/api/config", headers=th).status_code == 403

    # unauthenticated request rejected
    assert client.get("/api/info-sources").status_code == 401


def test_scheduled_job_flow_and_results_page_api(client, admin_headers, sync_worker, mock_llm, monkeypatch):
    # 三页合一后：定时分析配置并入任务编辑。避免后台调度真实触发。
    from app.backend.services import scheduler as sched_svc

    monkeypatch.setattr(sched_svc, "add_scheduled_job", lambda sj: None)
    monkeypatch.setattr(sched_svc, "reschedule_scheduled_job", lambda sj: None)
    monkeypatch.setattr(sched_svc, "remove_scheduled_job", lambda jid: None)

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

    # 通过任务编辑配置定时分析（间隔），并立即执行
    sj = client.put(
        f"/api/analysis-tasks/{tid}",
        json={"schedule": {"enabled": True, "mode": "incremental",
                           "trigger_type": "interval", "interval_seconds": 60}},
        headers=admin_headers,
    )
    assert sj.status_code == 200
    assert sj.json()["schedule"] is not None

    run = client.post(f"/api/analysis-tasks/{tid}/schedule/run", headers=admin_headers)
    assert run.status_code == 200
    rid = run.json()["run_id"]

    # 任务中心能按 ref_id 查到该 run
    runs = client.get(f"/api/task-center/runs?kind=analysis&ref_id={tid}", headers=admin_headers)
    assert any(r["id"] == rid for r in runs.json())

    # 结果详情页 API: 按任务取结果、按 run 取结果
    res = client.get(f"/api/analysis-tasks/{tid}/results?run_id={rid}", headers=admin_headers)
    assert res.status_code == 200

    # 全局结果端点已删除: GET 与 POST 均应 404(而非 405)
    gone = client.get("/api/analysis-results", headers=admin_headers)
    assert gone.status_code == 404
    assert client.post("/api/analysis-results", headers=admin_headers).status_code == 404

    # 清理: 删除定时配置（schedule:null）
    clr = client.put(f"/api/analysis-tasks/{tid}", json={"schedule": None}, headers=admin_headers)
    assert clr.status_code == 200
    assert clr.json()["schedule"] is None


def test_push_flow(client, admin_headers, sync_worker, mock_llm, monkeypatch):
    """端到端推送冒烟：配 SMTP -> 任务编辑配推送 -> 手动触发 -> 历史记录正确（mock 邮件发送）。"""
    # mock 邮件发送，避免真实 SMTP
    from app.backend.services.push.channels import email_channel

    sent: list = []
    monkeypatch.setattr(
        email_channel.EmailChannel,
        "send",
        lambda self, cfg, recipients, subject, html, text, attachments=None: sent.append((list(recipients), subject)),
    )

    # 建源 + 同步 + 任务 + 跑出分析结果
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
    assert len(client.get(f"/api/analysis-tasks/{tid}/results", headers=admin_headers).json()) == 1

    # 配置 SMTP（页面优先）
    r = client.put(
        "/api/push/smtp",
        headers=admin_headers,
        json={"host": "smtp.x.com", "port": 587, "from_email": "n@x.com", "password": "pw"},
    )
    assert r.status_code == 200

    # 通过任务编辑配置推送（手动触发，选 per_item）
    up = client.put(
        f"/api/analysis-tasks/{tid}",
        headers=admin_headers,
        json={"push": {"enabled": True, "event_types": ["per_item"],
                       "recipients": ["to@x.com"], "trigger_mode": "manual"}},
    )
    assert up.status_code == 200
    assert up.json()["push"] is not None

    # 手动触发 -> 同步执行推送
    trig = client.post(f"/api/analysis-tasks/{tid}/push/trigger", headers=admin_headers)
    assert trig.status_code == 200
    assert trig.json()["ok"] is True

    # 历史应为成功、事件数=1、收件人正确
    runs = client.get(f"/api/analysis-tasks/{tid}/push/runs", headers=admin_headers).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["event_count"] == 1
    assert sent and sent[0][0] == ["to@x.com"]
