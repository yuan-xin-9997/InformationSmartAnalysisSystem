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


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
