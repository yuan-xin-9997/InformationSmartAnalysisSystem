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
