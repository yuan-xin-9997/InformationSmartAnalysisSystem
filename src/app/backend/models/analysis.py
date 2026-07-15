"""Analysis-task, task-source (watermark) and analysis-result models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.timeutil import utcnow
from .info_source import InfoSource


class AnalysisTask(Base):
    """A user-defined analysis task binding one or more info sources."""

    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    task_sources: Mapped[list["TaskSource"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskSource(Base):
    """A source bound to a task, with an incremental-analysis watermark."""

    __tablename__ = "task_sources"
    __table_args__ = (UniqueConstraint("task_id", "source_id", name="uq_task_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("info_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    last_analyzed_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[AnalysisTask] = relationship(back_populates="task_sources")
    source: Mapped[InfoSource] = relationship()


class AnalysisResult(Base):
    """An LLM analysis output for a task run (per-item or aggregate)."""

    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_run_id: Mapped[int] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("info_sources.id", ondelete="SET NULL"), nullable=True
    )
    info_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("info_items.id", ondelete="SET NULL"), nullable=True
    )
    result_type: Mapped[str] = mapped_column(String(16), nullable=False)  # per_item|aggregate
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
