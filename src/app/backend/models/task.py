"""Task-run and task-log models (drives the 任务中心 page).

A ``TaskRun`` is any background execution: an analysis task run or an info
source sync. ``kind`` distinguishes them; ``ref_id`` points at the originating
analysis-task or info-source row.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.timeutil import utcnow


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # analysis | sync
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ref_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # full | incremental
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending | running | succeeded | failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    logs: Mapped[list["TaskLog"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="TaskLog.id"
    )


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[TaskRun | None] = relationship(back_populates="logs")
