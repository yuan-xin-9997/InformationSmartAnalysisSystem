"""ScheduledJob model + task_runs migration tests."""
from __future__ import annotations

from sqlalchemy import inspect

from app.backend.core.database import _ensure_column, engine


def test_scheduled_job_create_and_cascade(client, admin_headers):
    # 建任务
    t = client.post(
        "/api/analysis-tasks",
        json={"name": "t", "config": {"mode": "per_item"}, "source_ids": []},
        headers=admin_headers,
    )
    assert t.status_code == 201
    tid = t.json()["id"]
    # 直接写一条 ScheduledJob（API 在后续任务实现，此处用 ORM）
    from app.backend.core.database import SessionLocal
    from app.backend.models.scheduled_job import ScheduledJob

    with SessionLocal() as db:
        db.add(ScheduledJob(task_id=tid, name="j1", mode="incremental", trigger_type="interval", interval_seconds=60))
        db.commit()
    # 删除任务应级联删除定时任务
    d = client.delete(f"/api/analysis-tasks/{tid}", headers=admin_headers)
    assert d.status_code == 200
    with SessionLocal() as db:
        assert db.query(ScheduledJob).count() == 0


def test_task_run_has_scheduled_job_id_column():
    # 该测试不使用 client fixture，需自行确保表已建好
    from app.backend.core.database import init_db

    init_db()
    cols = [c["name"] for c in inspect(engine).get_columns("task_runs")]
    assert "scheduled_job_id" in cols


def test_ensure_column_idempotent():
    # 该测试不使用 client fixture，需自行确保表已建好
    from app.backend.core.database import init_db

    init_db()
    _ensure_column(engine, "task_runs", "scheduled_job_id", "INTEGER")
    cols = [c["name"] for c in inspect(engine).get_columns("task_runs")]
    assert "scheduled_job_id" in cols  # 再次调用不报错


def test_ensure_column_adds_missing():
    # 在一个临时表上验证加列逻辑
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS _tmp_test (id INTEGER)")
    _ensure_column(engine, "_tmp_test", "extra", "INTEGER")
    cols = [c["name"] for c in inspect(engine).get_columns("_tmp_test")]
    assert "extra" in cols
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE _tmp_test")
