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

    # 对照样本：第二个 task + run，ref_id 不同
    t2 = client.post(
        "/api/analysis-tasks",
        json={"name": "t2", "config": {"mode": "per_item"}, "source_ids": [sid]},
        headers=admin_headers,
    )
    assert t2.status_code == 201, t2.text
    tid2 = t2.json()["id"]
    run2 = client.post(
        f"/api/analysis-tasks/{tid2}/run", json={"mode": "incremental"}, headers=admin_headers
    )
    assert run2.status_code == 200, run2.text
    rid2 = run2.json()["run_id"]

    # 按 ref_id 过滤只返回该任务的 run；对照 run 必须被排除
    r = client.get(f"/api/task-center/runs?kind=analysis&ref_id={tid}", headers=admin_headers)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert rid in ids
    assert rid2 not in ids  # 对照 run 被排除
    assert all(x["ref_id"] == tid for x in r.json())
