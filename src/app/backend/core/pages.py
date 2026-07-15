"""Page (frontend route) definitions and permission keys.

Used by both backend access control and the permissions-management UI.
"""
from __future__ import annotations

# All pages in the sidebar. ``label`` is the Chinese display name.
PAGE_DEFINITIONS: list[dict[str, str | bool]] = [
    {"key": "dashboard", "label": "概览", "grantable": True},
    {"key": "info_sources", "label": "信息源管理", "grantable": True},
    {"key": "analysis_tasks", "label": "分析任务", "grantable": True},
    {"key": "analysis_result", "label": "分析结果", "grantable": True},
    {"key": "task_center", "label": "任务中心", "grantable": True},
    {"key": "system_config", "label": "系统配置", "grantable": True},
    {"key": "permission", "label": "权限管理", "grantable": False},  # admin only
]

ALL_PAGE_KEYS: list[str] = [p["key"] for p in PAGE_DEFINITIONS]  # type: ignore[misc]
ADMIN_ONLY_PAGE_KEYS: set[str] = {
    p["key"] for p in PAGE_DEFINITIONS if not p["grantable"]  # type: ignore[misc]
}
GRANTABLE_PAGE_KEYS: list[str] = [
    p["key"] for p in PAGE_DEFINITIONS if p["grantable"]  # type: ignore[misc]
]


def page_label(key: str) -> str:
    for p in PAGE_DEFINITIONS:
        if p["key"] == key:
            return str(p["label"])
    return key
