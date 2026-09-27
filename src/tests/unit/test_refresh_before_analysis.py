"""Analysis input freshness and failure isolation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

from app.backend.core.database import SessionLocal
from app.backend.models.analysis import AnalysisTask, TaskSource
from app.backend.models.info_source import InfoSource
from app.backend.models.task import TaskRun
from app.backend.services.info_source import refresh as refresh_module
from app.backend.services.info_source.base import InfoItemData


def _task(client, headers, ids, config=None):
    response = client.post("/api/analysis-tasks", headers=headers,
                           json={"name": "fresh", "source_ids": ids, "config": config or {}})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run(client, headers, task_id):
    response = client.post(f"/api/analysis-tasks/{task_id}/run", headers=headers,
                           json={"mode": "incremental"})
    assert response.status_code == 200, response.text
    return client.get(f"/api/task-center/runs/{response.json()['run_id']}", headers=headers).json()


def test_local_file_found_before_analysis_and_not_reanalyzed(client, admin_headers, sync_worker, mock_llm, tmp_path):
    source = client.post("/api/info-sources", headers=admin_headers,
                         json={"name": "folder", "type": "local_folder",
                               "config": {"folder_path": str(tmp_path), "patterns": ["*.txt"]}}).json()
    task_id = _task(client, admin_headers, [source["id"]])
    (tmp_path / "new.txt").write_text("new content", encoding="utf-8")
    first = _run(client, admin_headers, task_id)
    assert first["status"] == "succeeded"
    assert first["refresh_detail"]["sources"][0]["added_count"] == 1
    assert "处理 1 条" in first["summary"]
    second = _run(client, admin_headers, task_id)
    assert "处理 0 条" in second["summary"]
    assert second["refresh_detail"]["sources"][0]["added_count"] == 0
    assert len(mock_llm) == 1


def test_disabled_refresh_and_old_task_default(client, admin_headers, sync_worker, mock_llm, tmp_path):
    source = client.post("/api/info-sources", headers=admin_headers,
                         json={"name": "folder", "type": "local_folder",
                               "config": {"folder_path": str(tmp_path)}}).json()
    disabled = _task(client, admin_headers, [source["id"]], {"refresh_before_run": False})
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    run = _run(client, admin_headers, disabled)
    assert run["refresh_detail"]["sources"] == []
    assert "处理 0 条" in run["summary"]
    legacy = _task(client, admin_headers, [source["id"]])
    assert "处理 1 条" in _run(client, admin_headers, legacy)["summary"]


def test_fresh_network_source_skips_fetch(client, admin_headers, sync_worker, mock_llm, monkeypatch):
    from app.backend.core.timeutil import utcnow
    source = InfoSource(name="feed", type="freshrss", config={"base_url": "unused"},
                        status="ok", last_sync_at=utcnow())
    with SessionLocal() as db:
        db.add(source)
        db.commit()
        sid = source.id
    task_id = _task(client, admin_headers, [sid])
    monkeypatch.setattr(refresh_module, "run_sync", lambda *_: (_ for _ in ()).throw(AssertionError("unexpected fetch")))
    run = _run(client, admin_headers, task_id)
    assert run["refresh_detail"]["sources"][0]["status"] == "skipped"


def test_partial_failure_continues_and_releases_lock(client, admin_headers, sync_worker, mock_llm, tmp_path, monkeypatch):
    good = client.post("/api/info-sources", headers=admin_headers,
                       json={"name": "good", "type": "local_folder",
                             "config": {"folder_path": str(tmp_path)}}).json()["id"]
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    with SessionLocal() as db:
        bad = InfoSource(name="bad", type="freshrss", config={"base_url": "unused"})
        db.add(bad)
        db.commit()
        bad_id = bad.id
    task_id = _task(client, admin_headers, [bad_id, good])
    original = refresh_module.run_sync
    def fail_bad(run_id, source_id, **kwargs):
        if source_id == bad_id:
            raise RuntimeError("secret=do-not-show")
        return original(run_id, source_id, **kwargs)
    monkeypatch.setattr(refresh_module, "run_sync", fail_bad)
    run = _run(client, admin_headers, task_id)
    assert run["status"] == "succeeded"
    assert "部分更新失败" in run["summary"]
    assert "处理 1 条" in run["summary"]
    assert "do-not-show" not in str(run)
    # The exception leaves the per-source lock available for a later attempt.
    monkeypatch.setattr(refresh_module, "run_sync", original)
    assert refresh_module.source_lock(bad_id).acquire(blocking=False)
    refresh_module.source_lock(bad_id).release()


def test_shared_source_serializes_update(client, admin_headers, monkeypatch):
    with SessionLocal() as db:
        source = InfoSource(name="feed", type="freshrss", config={"base_url": "unused"})
        db.add(source)
        db.commit()
        sid = source.id
    calls = []
    calls_lock = Lock()
    def fake_sync(run_id, source_id, **kwargs):
        with calls_lock:
            calls.append(source_id)
        time.sleep(0.05)
        with SessionLocal() as db:
            run = db.get(TaskRun, run_id)
            src = db.get(InfoSource, source_id)
            src.status = "ok"
            src.last_sync_at = __import__("app.backend.core.timeutil", fromlist=["utcnow"]).utcnow()
            run.status = "succeeded"
            run.refresh_detail = {"added_count": 1, "updated_count": 0}
            db.commit()
    monkeypatch.setattr(refresh_module, "run_sync", fake_sync)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: refresh_module.refresh(sid), range(2)))
    assert len(calls) == 1
    assert sorted(r.status for r in results) == ["skipped", "succeeded"]


def test_network_sources_only_analyze_new_entries(client, admin_headers, sync_worker, mock_llm, monkeypatch):
    from app.backend.services.info_source import sync
    entries = {"website": ["a"], "freshrss": ["a"]}
    class Adapter:
        def __init__(self, kind):
            self.kind = kind
        def fetch_new_items(self, since=None, known_ids=None):
            return [InfoItemData(external_id=f"https://example.org/{name}" if self.kind == "website" else name,
                                 title=name, content=name)
                    for name in entries[self.kind]
                    if (f"https://example.org/{name}" if self.kind == "website" else name) not in (known_ids or set())]
    monkeypatch.setattr(sync, "get_adapter", lambda kind, config: Adapter(kind))
    ids = []
    with SessionLocal() as db:
        for kind, config in (("website", {"sites": [{"name": "site", "url": "https://example.org/news"}]}),
                             ("freshrss", {"base_url": "unused"})):
            src = InfoSource(name=kind, type=kind, config=config)
            db.add(src)
            db.flush()
            ids.append(src.id)
        db.commit()
    task_id = _task(client, admin_headers, ids, {"refresh_max_age_seconds": 0})
    assert "处理 2 条" in _run(client, admin_headers, task_id)["summary"]
    assert "处理 0 条" in _run(client, admin_headers, task_id)["summary"]
    entries["website"].append("b")
    entries["freshrss"].append("b")
    third = _run(client, admin_headers, task_id)
    assert "处理 2 条" in third["summary"]
    assert [r["added_count"] for r in third["refresh_detail"]["sources"]] == [1, 1]
    assert len(mock_llm) == 4
