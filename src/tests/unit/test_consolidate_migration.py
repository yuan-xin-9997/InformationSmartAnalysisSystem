"""Tests for the consolidation migration (consolidate-task-analysis-page).

Covers: multi-task push-rule split (watermark copied verbatim), single-task
backfill, empty-task rule deletion, duplicate scheduled-job / push-rule
collapse, page-permission migration, unique-index creation, and idempotency.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.backend.core.database import (
    _ensure_column,
    _migrate_consolidate_task_analysis,
)


def _build_legacy_engine():
    """A file-based DB with the PRE-consolidation schema + legacy rows.

    Uses a temp file (not ``:memory:``) so the connection pool shares one
    database across ``begin()`` blocks, matching production SQLite behaviour;
    ``:memory:`` is connection-local and gives non-deterministic state across
    pooled connections in multi-statement migrations.
    """
    db_path = Path(tempfile.gettempdir()) / f"isas_migration_{uuid.uuid4().hex}.sqlite3"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as conn:
        # Legacy push_rules: multi-task via task_ids JSON array, no task_id column.
        conn.execute(
            text(
                "CREATE TABLE push_rules ("
                "id INTEGER PRIMARY KEY, name VARCHAR(128) NOT NULL, "
                "channel VARCHAR(32) NOT NULL DEFAULT 'email', "
                "task_ids TEXT NOT NULL, event_types TEXT NOT NULL, "
                "recipients TEXT NOT NULL, trigger_mode VARCHAR(16) NOT NULL, "
                "cron_expr VARCHAR(128), interval_seconds INTEGER, "
                "enabled BOOLEAN NOT NULL DEFAULT 1, last_pushed_result_id INTEGER, "
                "max_events_per_email INTEGER NOT NULL DEFAULT 50, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
        # Rule 1: multi-task [1, 2], watermark 100.
        conn.execute(
            text(
                "INSERT INTO push_rules (id, name, task_ids, event_types, recipients, "
                "trigger_mode, enabled, last_pushed_result_id, max_events_per_email, created_at, updated_at) "
                "VALUES (1, '多任务', '[1,2]', '[\"per_item\"]', '[\"a@x.com\"]', "
                "'on_run', 1, 100, 50, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        # Rule 2: single-task [3], no watermark yet.
        conn.execute(
            text(
                "INSERT INTO push_rules (id, name, task_ids, event_types, recipients, "
                "trigger_mode, enabled, last_pushed_result_id, max_events_per_email, created_at, updated_at) "
                "VALUES (2, '单任务', '[3]', '[\"aggregate\"]', '[\"b@x.com\"]', "
                "'scheduled', 1, NULL, 50, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        # Rule 3: empty task_ids [] -- orphan to be deleted.
        conn.execute(
            text(
                "INSERT INTO push_rules (id, name, task_ids, event_types, recipients, "
                "trigger_mode, enabled, last_pushed_result_id, max_events_per_email, created_at, updated_at) "
                "VALUES (3, '空任务', '[]', '[\"per_item\"]', '[\"c@x.com\"]', "
                "'manual', 1, NULL, 50, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        # Rule 4 & 5: two legacy rules BOTH covering task 7 -- collapse to one.
        conn.execute(
            text(
                "INSERT INTO push_rules (id, name, task_ids, event_types, recipients, "
                "trigger_mode, enabled, last_pushed_result_id, max_events_per_email, created_at, updated_at) "
                "VALUES (4, '重复A', '[7]', '[\"per_item\"]', '[\"d@x.com\"]', "
                "'on_run', 1, 50, 50, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO push_rules (id, name, task_ids, event_types, recipients, "
                "trigger_mode, enabled, last_pushed_result_id, max_events_per_email, created_at, updated_at) "
                "VALUES (5, '重复B', '[7]', '[\"per_item\"]', '[\"e@x.com\"]', "
                "'on_run', 1, 80, 50, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )

        # Legacy scheduled_jobs: task 5 has two jobs (collapse to newest).
        conn.execute(
            text(
                "CREATE TABLE scheduled_jobs ("
                "id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, "
                "name VARCHAR(128) NOT NULL, mode VARCHAR(16) NOT NULL, "
                "trigger_type VARCHAR(16) NOT NULL, cron_expr VARCHAR(128), "
                "interval_seconds INTEGER, enabled BOOLEAN NOT NULL DEFAULT 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO scheduled_jobs (id, task_id, name, mode, trigger_type, "
                "cron_expr, enabled) VALUES (10, 5, '早', 'incremental', 'cron', "
                "'0 8 * * *', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO scheduled_jobs (id, task_id, name, mode, trigger_type, "
                "cron_expr, enabled) VALUES (11, 5, '晚', 'incremental', 'cron', "
                "'0 9 * * *', 1)"
            )
        )

        # Legacy page_permissions: user 1 had push_management, user 2 had
        # scheduled_jobs, user 3 already had analysis_tasks.
        conn.execute(
            text(
                "CREATE TABLE page_permissions ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "page_key VARCHAR(64) NOT NULL, "
                "UNIQUE (user_id, page_key))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO page_permissions (user_id, page_key) VALUES "
                "(1, 'push_management'), (2, 'scheduled_jobs'), (3, 'analysis_tasks')"
            )
        )
    return eng


def _prepare(eng):
    """Add the task_id column (as init_db would) then run the migration."""
    _ensure_column(eng, "push_rules", "task_id", "INTEGER")
    _migrate_consolidate_task_analysis(eng)


def test_multi_task_rule_split_with_watermark_copied():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        rows = conn.execute(
            text("SELECT task_id, last_pushed_result_id, recipients FROM push_rules "
                 "WHERE task_id IN (1, 2) ORDER BY task_id")
        ).fetchall()
    assert len(rows) == 2
    assert {r[0] for r in rows} == {1, 2}
    # Watermark copied verbatim from the original multi-task rule.
    assert all(r[1] == 100 for r in rows)


def test_single_task_rule_backfilled():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        row = conn.execute(
            text("SELECT task_id, trigger_mode FROM push_rules WHERE task_id = 3")
        ).fetchone()
    assert row is not None
    assert row[0] == 3
    assert row[1] == "scheduled"


def test_empty_task_ids_rule_deleted():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM push_rules WHERE name = '空任务'")).fetchone()
    assert n[0] == 0


def test_duplicate_push_rules_same_task_collapsed():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM push_rules WHERE task_id = 7")
        ).fetchone()
        kept = conn.execute(
            text("SELECT name FROM push_rules WHERE task_id = 7")
        ).fetchone()
    assert n[0] == 1
    assert kept[0] == "重复B"  # newest (max id) kept


def test_duplicate_scheduled_jobs_collapsed():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM scheduled_jobs WHERE task_id = 5")
        ).fetchone()
        kept = conn.execute(
            text("SELECT name FROM scheduled_jobs WHERE task_id = 5")
        ).fetchone()
    assert n[0] == 1
    assert kept[0] == "晚"  # newest (max id) kept


def test_page_permission_migration():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        u1 = conn.execute(
            text("SELECT page_key FROM page_permissions WHERE user_id = 1")
        ).fetchall()
        u2 = conn.execute(
            text("SELECT page_key FROM page_permissions WHERE user_id = 2")
        ).fetchall()
        u3 = conn.execute(
            text("SELECT page_key FROM page_permissions WHERE user_id = 3")
        ).fetchall()
        legacy = conn.execute(
            text("SELECT COUNT(*) FROM page_permissions "
                 "WHERE page_key IN ('scheduled_jobs', 'push_management')")
        ).fetchone()
    assert {r[0] for r in u1} == {"analysis_tasks"}
    assert {r[0] for r in u2} == {"analysis_tasks"}
    assert {r[0] for r in u3} == {"analysis_tasks"}  # unchanged, already had it
    assert legacy[0] == 0


def test_unique_indexes_created():
    eng = _build_legacy_engine()
    _prepare(eng)
    sj_idx = {i["name"] for i in inspect(eng).get_indexes("scheduled_jobs")}
    pr_idx = {i["name"] for i in inspect(eng).get_indexes("push_rules")}
    assert "uq_scheduled_jobs_task_id" in sj_idx
    assert "uq_push_rules_task_id" in pr_idx


def test_migration_idempotent():
    eng = _build_legacy_engine()
    _prepare(eng)
    with eng.begin() as conn:
        before_pr = conn.execute(text("SELECT COUNT(*) FROM push_rules")).fetchone()[0]
        before_sj = conn.execute(text("SELECT COUNT(*) FROM scheduled_jobs")).fetchone()[0]
    _migrate_consolidate_task_analysis(eng)  # second run
    with eng.begin() as conn:
        after_pr = conn.execute(text("SELECT COUNT(*) FROM push_rules")).fetchone()[0]
        after_sj = conn.execute(text("SELECT COUNT(*) FROM scheduled_jobs")).fetchone()[0]
    assert before_pr == after_pr
    assert before_sj == after_sj


def test_fresh_db_no_legacy_column_is_noop():
    """A fresh DB (no task_ids column) must skip the split and still build indexes."""
    db_path = Path(tempfile.gettempdir()) / f"isas_fresh_{uuid.uuid4().hex}.sqlite3"
    eng = create_engine(f"sqlite:///{db_path}")
    with eng.begin() as conn:
        # New-schema push_rules: has task_id, no task_ids.
        conn.execute(
            text(
                "CREATE TABLE push_rules (id INTEGER PRIMARY KEY, task_id INTEGER, "
                "name VARCHAR(128) NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE scheduled_jobs (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL)"
            )
        )
    _migrate_consolidate_task_analysis(eng)  # must not raise
    pr_idx = {i["name"] for i in inspect(eng).get_indexes("push_rules")}
    assert "uq_push_rules_task_id" in pr_idx
