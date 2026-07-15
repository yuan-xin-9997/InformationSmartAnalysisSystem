"""Time-conversion unit tests (CLAUDE.md 规范2: display Beijing time)."""
from __future__ import annotations

from datetime import datetime, timezone


def test_to_beijing_adds_8_hours():
    from app.backend.core.timeutil import to_beijing

    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    bj = to_beijing(dt)
    assert bj.hour == 8
    assert str(bj.tzinfo)  # tz-aware


def test_naive_datetime_treated_as_utc():
    from app.backend.core.timeutil import to_beijing

    dt = datetime(2026, 1, 1, 0, 0, 0)  # naive
    assert to_beijing(dt).hour == 8


def test_format_beijing():
    from app.backend.core.timeutil import format_beijing

    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert format_beijing(dt) == "2026-01-01 08:00:00"


def test_format_none():
    from app.backend.core.timeutil import format_beijing

    assert format_beijing(None) is None
