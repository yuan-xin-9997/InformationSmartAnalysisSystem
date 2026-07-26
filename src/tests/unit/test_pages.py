"""Page key registry tests."""
from __future__ import annotations

from app.backend.core.pages import ALL_PAGE_KEYS, GRANTABLE_PAGE_KEYS


def test_analysis_result_removed():
    assert "analysis_result" not in ALL_PAGE_KEYS
    assert "analysis_result" not in GRANTABLE_PAGE_KEYS


def test_scheduled_jobs_present():
    assert "scheduled_jobs" in ALL_PAGE_KEYS
    assert "scheduled_jobs" in GRANTABLE_PAGE_KEYS
