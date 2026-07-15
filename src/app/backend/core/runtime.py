"""Process-runtime info (in-memory, reset on each start)."""
from __future__ import annotations

from datetime import datetime

_started_at: datetime | None = None


def set_started_at(dt: datetime) -> None:
    global _started_at
    _started_at = dt


def get_started_at() -> datetime | None:
    return _started_at
