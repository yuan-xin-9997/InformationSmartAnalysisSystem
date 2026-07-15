"""Time helpers.

All timestamps are stored as timezone-aware UTC in the database. Anything shown
to the user is converted to Beijing time (Asia/Shanghai), per CLAUDE.md 规范2.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
BEIJING = ZoneInfo("Asia/Shanghai")


def utcnow() -> datetime:
    """Current time as timezone-aware UTC."""
    return datetime.now(UTC)


def to_beijing(dt: datetime) -> datetime:
    """Convert a datetime to Beijing time. Naive datetimes assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(BEIJING)


def format_beijing(dt: datetime | None) -> str | None:
    """``YYYY-MM-DD HH:MM:SS`` in Beijing time, or None."""
    if dt is None:
        return None
    return to_beijing(dt).strftime("%Y-%m-%d %H:%M:%S")


def iso_beijing(dt: datetime | None) -> str | None:
    """ISO 8601 string in Beijing time, or None."""
    if dt is None:
        return None
    return to_beijing(dt).isoformat()
