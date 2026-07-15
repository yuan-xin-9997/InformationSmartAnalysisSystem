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
