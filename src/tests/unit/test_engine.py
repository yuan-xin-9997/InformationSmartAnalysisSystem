"""Analysis engine unit tests: incremental watermark, full, aggregate modes."""
from __future__ import annotations

import pathlib
import tempfile


def _make_folder_source(client, headers, files: dict[str, str]) -> int:
    d = pathlib.Path(tempfile.mkdtemp())
    for name, body in files.items():
        (d / name).write_text(body, encoding="utf-8")
    r = client.post(
        "/api/info-sources",
        headers=headers,
        json={
            "name": "s",
            "type": "local_folder",
            "config": {"folder_path": str(d), "patterns": ["*.txt"]},
        },
    )
    sid = r.json()["id"]
    client.post(f"/api/info-sources/{sid}/sync", headers=headers)
    return sid


def _run(client, headers, task_id, mode):
    r = client.post(
        f"/api/analysis-tasks/{task_id}/run", headers=headers, json={"mode": mode}
    )
    run_id = r.json()["run_id"]
    return client.get(f"/api/task-center/runs/{run_id}", headers=headers).json()


def test_incremental_then_full_and_aggregate(client, admin_headers, sync_worker, mock_llm):
    sid = _make_folder_source(client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B"})

    tid = client.post(
        "/api/analysis-tasks",
        headers=admin_headers,
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": [sid]},
    ).json()["id"]

    # 1st incremental -> analyzes both new items
    run1 = _run(client, admin_headers, tid, "incremental")
    assert run1["status"] == "succeeded"
    assert "处理 2 条" in run1["summary"]
    res = client.get(f"/api/analysis-tasks/{tid}/results", headers=admin_headers).json()
    assert len(res) == 2

    # 2nd incremental -> watermark blocks re-analysis (0 items)
    run2 = _run(client, admin_headers, tid, "incremental")
    assert "处理 0 条" in run2["summary"]

    # full -> re-analyzes all
    run3 = _run(client, admin_headers, tid, "full")
    assert "处理 2 条" in run3["summary"]

    # aggregate mode -> one summary result
    client.put(
        f"/api/analysis-tasks/{tid}",
        headers=admin_headers,
        json={"config": {"mode": "aggregate"}},
    )
    run4 = _run(client, admin_headers, tid, "full")
    assert "生成 1 条结果" in run4["summary"]
    res = client.get(f"/api/analysis-tasks/{tid}/results", headers=admin_headers).json()
    assert any(r["result_type"] == "aggregate" for r in res)

    # watermark recorded on the task-source
    sources = client.get(
        f"/api/analysis-tasks/{tid}/sources", headers=admin_headers
    ).json()
    assert sources[0]["last_analyzed_item_id"] is not None


def test_dedup_on_resync(client, admin_headers, sync_worker, mock_llm):
    sid = _make_folder_source(client, admin_headers, {"x.txt": "内容X"})
    # sync again -> no new items (dedup by external_id)
    client.post(f"/api/info-sources/{sid}/sync", headers=admin_headers)
    status = client.get(f"/api/info-sources/{sid}/status", headers=admin_headers).json()
    assert status["item_count"] == 1


def test_custom_mode_analyzes_selected_items(client, admin_headers, sync_worker, mock_llm):
    sid = _make_folder_source(client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B", "c.txt": "内容C"})
    items = client.get(f"/api/info-sources/{sid}/items?limit=10", headers=admin_headers).json()
    assert len(items) == 3
    selected = [items[0]["id"], items[1]["id"]]

    tid = client.post(
        "/api/analysis-tasks",
        headers=admin_headers,
        json={"name": "custom", "config": {"mode": "custom", "custom_item_ids": selected}, "source_ids": [sid]},
    ).json()["id"]
    run = client.post(f"/api/analysis-tasks/{tid}/run", headers=admin_headers, json={"mode": "custom"}).json()
    rd = client.get(f"/api/task-center/runs/{run['run_id']}", headers=admin_headers).json()
    assert rd["status"] == "succeeded"
    assert "处理 2 条" in rd["summary"]
    assert rd["mode"] == "custom"

    res = client.get(f"/api/analysis-tasks/{tid}/results", headers=admin_headers).json()
    assert len(res) == 2
    assert sorted(r["info_item_id"] for r in res) == sorted(selected)

    # 自定义模式不推进水位线
    sources = client.get(f"/api/analysis-tasks/{tid}/sources", headers=admin_headers).json()
    assert sources[0]["last_analyzed_item_id"] is None


def test_delete_task_cascades_results(client, admin_headers, sync_worker, mock_llm):
    """SQLite 需开启 PRAGMA foreign_keys=ON 才会级联删除；删除任务应清除其分析结果。"""
    from app.backend.core.database import SessionLocal
    from app.backend.models.analysis import AnalysisResult

    sid = _make_folder_source(client, admin_headers, {"a.txt": "内容A"})
    tid = client.post(
        "/api/analysis-tasks",
        headers=admin_headers,
        json={"name": "cascade", "config": {"mode": "per_item"}, "source_ids": [sid]},
    ).json()["id"]
    run = client.post(f"/api/analysis-tasks/{tid}/run", headers=admin_headers, json={"mode": "incremental"}).json()
    rd = client.get(f"/api/task-center/runs/{run['run_id']}", headers=admin_headers).json()
    assert rd["status"] == "succeeded"

    with SessionLocal() as db:
        assert db.query(AnalysisResult).filter(AnalysisResult.task_id == tid).count() == 1

    client.delete(f"/api/analysis-tasks/{tid}", headers=admin_headers)

    with SessionLocal() as db:
        assert db.query(AnalysisResult).filter(AnalysisResult.task_id == tid).count() == 0
