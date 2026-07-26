"""Push email rendering tests."""
from __future__ import annotations

from datetime import datetime, timezone

from app.backend.services.push.render import PushEvent, render_events


def test_render_includes_count_and_beijing_time():
    events = [
        PushEvent(
            task_name="任务A",
            result_type="per_item",
            source_name="源1",
            content="关键事件X",
            created_at=datetime(2026, 7, 26, 3, 0, tzinfo=timezone.utc),
        )
    ]
    subject, html, text = render_events("我的规则", events)
    assert "1条新事件" in subject
    assert "我的规则" in subject
    assert "任务A" in html
    assert "逐条分析" in html
    assert "关键事件X" in html
    # UTC 03:00 -> 北京时间 11:00
    assert "11:00" in html
    assert "11:00" in text


def test_render_escapes_html_in_content():
    events = [
        PushEvent(
            task_name="T",
            result_type="aggregate",
            source_name="S",
            content="<script>alert(1)</script>",
            created_at=datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc),
        )
    ]
    _, html, _ = render_events("r", events)
    assert "<script>" not in html  # 内容被转义
    assert "&lt;script&gt;" in html


def test_render_aggregate_label():
    events = [
        PushEvent(
            task_name="T",
            result_type="aggregate",
            source_name="S",
            content="c",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    ]
    _, html, _ = render_events("r", events)
    assert "汇总分析" in html
