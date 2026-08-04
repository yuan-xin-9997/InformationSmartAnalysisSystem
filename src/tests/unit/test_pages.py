"""Page key registry tests."""
from __future__ import annotations

from app.backend.core.pages import ALL_PAGE_KEYS, GRANTABLE_PAGE_KEYS


def test_analysis_result_removed():
    assert "analysis_result" not in ALL_PAGE_KEYS
    assert "analysis_result" not in GRANTABLE_PAGE_KEYS


def test_consolidated_pages_removed_scheduled_and_push():
    """三页合一后：scheduled_jobs / push_management 页面键移除。"""
    assert "scheduled_jobs" not in ALL_PAGE_KEYS
    assert "push_management" not in ALL_PAGE_KEYS
    assert "scheduled_jobs" not in GRANTABLE_PAGE_KEYS
    assert "push_management" not in GRANTABLE_PAGE_KEYS


def test_analysis_tasks_present_and_relabelled():
    from app.backend.core.pages import page_label

    assert "analysis_tasks" in ALL_PAGE_KEYS
    assert "analysis_tasks" in GRANTABLE_PAGE_KEYS
    assert page_label("analysis_tasks") == "任务分析"
