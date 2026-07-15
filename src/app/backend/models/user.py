"""User and page-permission ORM models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.timeutil import utcnow


class User(Base):
    """A loginable user, synced from ``data/password.txt``.

    ``password_hash`` is a bcrypt hash; ``password_fingerprint`` (sha256 of the
    plaintext) lets the sync skip re-hashing when the file is unchanged.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")  # admin | user
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    permissions: Mapped[list["PagePermission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PagePermission(Base):
    """A page a normal user is allowed to access (admin implicitly has all)."""

    __tablename__ = "page_permissions"
    __table_args__ = (UniqueConstraint("user_id", "page_key", name="uq_user_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_key: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship(back_populates="permissions")
