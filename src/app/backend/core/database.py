"""Database engine, declarative base, session factory."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


settings.database_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{settings.database_path}",
    connect_args={"check_same_thread": False},  # required for FastAPI threadpool
    echo=False,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite 默认关闭外键约束，导致 ondelete=CASCADE 不生效。每个连接开启它。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_column(engine_, table_name: str, column_name: str, column_ddl: str) -> None:
    """Add a column to an existing table if missing (lightweight migration for
    tables created before the column existed). No-op for missing tables
    (create_all will build them fresh)."""
    insp = inspect(engine_)
    if not insp.has_table(table_name):
        return
    existing = {c["name"] for c in insp.get_columns(table_name)}
    if column_name not in existing:
        with engine_.begin() as conn:
            conn.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}")
            )


def init_db() -> None:
    """Create all tables. Imports models so they register on ``Base``."""
    from .. import models  # noqa: F401  (registers ORM models)

    Base.metadata.create_all(bind=engine)
    # Migrate pre-existing tables (create_all does not ALTER existing tables).
    _ensure_column(engine, "task_runs", "scheduled_job_id", "INTEGER")
    # InfoItem article-metadata columns (task 1: optimize-analysis-result-page).
    _ensure_column(engine, "info_items", "author", "TEXT")
    _ensure_column(engine, "info_items", "author_affiliation", "TEXT")
    _ensure_column(engine, "info_items", "article_published_at", "DATETIME")
    _ensure_column(engine, "info_items", "page_count", "INTEGER")
    # InfoItem 正文抽取来源（enhance-pdf-content-extraction）。
    _ensure_column(engine, "info_items", "extraction_method", "TEXT")
    # 推送规则 1:1 化（consolidate-task-analysis-page）：新增 task_id 列。
    _ensure_column(engine, "push_rules", "task_id", "INTEGER")
    # 三页合一迁移：拆分多任务推送规则、收敛多余定时、迁移页面权限、建唯一索引。
    _migrate_consolidate_task_analysis(engine)


def _collapse_dup_by_task_id(conn, table: str) -> None:
    """每个 task_id 若有多行，保留最新（max id）一行，删除其余。

    在创建唯一索引前去重，保证 ``CREATE UNIQUE INDEX`` 不因重复而失败。
    ``table`` 仅为模块内常量字面量，不接受外部输入。
    """
    dup = conn.execute(
        text(
            f"SELECT task_id FROM {table} WHERE task_id IS NOT NULL "
            f"GROUP BY task_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    for row in dup:
        tid = row[0]
        keep = conn.execute(
            text(
                f"SELECT id FROM {table} WHERE task_id = :tid ORDER BY id DESC LIMIT 1"
            ),
            {"tid": tid},
        ).first()
        keep_id = keep[0] if keep else None
        conn.execute(
            text(f"DELETE FROM {table} WHERE task_id = :tid AND id <> :keep"),
            {"tid": tid, "keep": keep_id},
        )


def _migrate_consolidate_task_analysis(engine_) -> None:
    """三页合一的一次性幂等迁移（consolidate-task-analysis-page）。

    - PushRule：把遗留多任务规则（``task_ids`` JSON 数组）按任务拆分为 1:1
      规则（水位线原样复制--``AnalysisResult.id`` 全局单调，安全），回填单任务
      规则的 ``task_id``，删除遗留行；之后每条 push_rule 的 ``task_id`` 非空。
    - ScheduledJob / PushRule：按 ``task_id`` 收敛重复行至最新一条。
    - PagePermission：曾持有 ``scheduled_jobs``/``push_management`` 的用户补授
      ``analysis_tasks``，并删除两个旧键。
    - 最后创建 ``scheduled_jobs.task_id`` 与 ``push_rules.task_id`` 唯一索引。

    幂等：以「遗留行存在（``task_id`` 为空且 ``task_ids`` 列存在并非空）」为哨兵，
    已迁移的库再次运行无副作用；全新库（无 ``task_ids`` 列）跳过拆分。
    """
    insp = inspect(engine_)
    if not insp.has_table("push_rules") or not insp.has_table("scheduled_jobs"):
        return  # 全新库由 create_all 直接建新结构，无需迁移

    push_cols = {c["name"] for c in insp.get_columns("push_rules")}
    if "task_id" not in push_cols:
        return  # _ensure_column 尚未执行，无可迁移
    has_legacy_task_ids = "task_ids" in push_cols  # 仅旧库有此列

    with engine_.begin() as conn:
        # 1. 拆分遗留多任务/单任务推送规则为 1:1（仅旧库）。
        if has_legacy_task_ids:
            conn.execute(
                text(
                    "INSERT INTO push_rules (name, channel, task_id, task_ids, event_types, "
                    "recipients, trigger_mode, cron_expr, interval_seconds, enabled, "
                    "last_pushed_result_id, max_events_per_email) "
                    "SELECT r.name, r.channel, CAST(je.value AS INTEGER), '[]', r.event_types, "
                    "r.recipients, r.trigger_mode, r.cron_expr, r.interval_seconds, r.enabled, "
                    "r.last_pushed_result_id, r.max_events_per_email "
                    "FROM push_rules r, json_each(r.task_ids) je "
                    "WHERE r.task_id IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM push_rules p2 "
                    "WHERE p2.task_id = CAST(je.value AS INTEGER))"
                )
            )
            # 删除所有遗留行（含 task_ids 为空数组者--无可归属任务）。
            conn.execute(
                text("DELETE FROM push_rules WHERE task_id IS NULL AND task_ids IS NOT NULL")
            )

        # 2. 按 task_id 收敛重复行（含拆分后同任务多规则的情况）。
        _collapse_dup_by_task_id(conn, "scheduled_jobs")
        _collapse_dup_by_task_id(conn, "push_rules")

        # 3. 页面权限迁移。
        if insp.has_table("page_permissions"):
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO page_permissions (user_id, page_key) "
                    "SELECT user_id, 'analysis_tasks' FROM page_permissions "
                    "WHERE page_key IN ('scheduled_jobs', 'push_management') "
                    "GROUP BY user_id"
                )
            )
            conn.execute(
                text(
                    "DELETE FROM page_permissions "
                    "WHERE page_key IN ('scheduled_jobs', 'push_management')"
                )
            )

    # 4. 去重后创建唯一索引（IF NOT EXISTS 保证幂等）。
    with engine_.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_scheduled_jobs_task_id "
                "ON scheduled_jobs(task_id)"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_push_rules_task_id "
                "ON push_rules(task_id)"
            )
        )


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
