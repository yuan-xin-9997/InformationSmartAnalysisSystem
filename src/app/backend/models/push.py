"""Push-rule, push-run (history) and SMTP-config models.

A ``PushRule`` is an admin-defined subscription belonging to exactly one
analysis task (1:1 via ``task_id``): which event types
(``AnalysisResult.result_type``), which recipients, and a trigger mode
(``on_run`` / ``scheduled`` / ``manual``). It carries a single watermark
``last_pushed_result_id`` (``AnalysisResult.id`` is globally monotonic, so one
value per rule correctly selects the incremental set for its task).

A ``PushRun`` records one push execution (succeeded / failed / no_new).

``SmtpConfig`` is a single-row (``id=1``) table that overrides the ``email``
section in ``app.json`` when present -- page config takes priority over file.

Note: the legacy ``task_ids`` JSON column (multi-task, N:M) is retained on the
DB for migration only and is intentionally NOT mapped on the ORM; the
consolidation migration (``core/database.py``) reads it via raw SQL, splits
multi-task rules into per-task 1:1 rules, then ignores it thereafter.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session

from ..core.database import Base
from ..core.timeutil import utcnow


class PushRule(Base):
    __tablename__ = "push_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recipients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    trigger_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # on_run|scheduled|manual
    cron_expr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_pushed_result_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_events_per_email: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    runs: Mapped[list["PushRun"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan", order_by="PushRun.id.desc()"
    )


class PushRun(Base):
    __tablename__ = "push_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("push_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    recipients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # succeeded|failed|no_new
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    rule: Mapped[PushRule | None] = relationship(back_populates="runs")


class SmtpConfig(Base):
    """Singleton SMTP configuration row (``id=1``). Page config overrides app.json."""

    __tablename__ = "smtp_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 固定为 1
    host: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    password: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    from_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    from_name: Mapped[str] = mapped_column(String(128), nullable=False, default="信息智能分析系统")


def get_smtp_config_row(db: Session) -> SmtpConfig:
    """Return the singleton SMTP config row (``id=1``), creating it if missing."""
    cfg = db.get(SmtpConfig, 1)
    if cfg is None:
        cfg = SmtpConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


__all__ = [
    "PushRule",
    "PushRun",
    "SmtpConfig",
    "get_smtp_config_row",
]


# Silence unused-import linter for Any (kept for type clarity on JSON columns).
_ = Any
