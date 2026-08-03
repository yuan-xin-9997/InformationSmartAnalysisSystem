"""Information-source and information-item models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.timeutil import utcnow


class InfoSource(Base):
    """A configured information source (website / local folder / FreshRSS)."""

    __tablename__ = "info_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # website|local_folder|freshrss
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok|warning|error
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    items: Mapped[list["InfoItem"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class InfoItem(Base):
    """A single piece of fetched information belonging to a source."""

    __tablename__ = "info_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("info_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Article metadata (nullable, populated by extraction in later tasks).
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    author_affiliation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    article_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 正文抽取来源：text_layer（PDF 文本层）/ vision_llm（视觉兜底）/ none（均未产出有效文本）。
    # NULL 表示历史遗留条目（尚未重抽）。
    extraction_method: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source: Mapped[InfoSource] = relationship(back_populates="items")
    figures: Mapped[list["InfoItemFigure"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class InfoItemFigure(Base):
    """A figure/image extracted from an InfoItem's source document."""

    __tablename__ = "info_item_figures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("info_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    figure_index: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caption: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    item: Mapped[InfoItem] = relationship(back_populates="figures")
