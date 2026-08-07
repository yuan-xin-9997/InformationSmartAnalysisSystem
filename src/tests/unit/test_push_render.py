"""Push email rendering tests."""
from __future__ import annotations

from datetime import datetime, timezone

from app.backend.services.push.attachments import InlineImage
from app.backend.services.push.render import PushEvent, render_events


def _fig(cid: str, item_id: int = 1, mime: str = "image/png") -> InlineImage:
    return InlineImage(cid=cid, filename=f"{cid}.png", mime=mime, data=b"\x89PNG", item_id=item_id)


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
    subject, html, text, _ = render_events("我的规则", events)
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
    _, html, _, _ = render_events("r", events)
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
    _, html, _, _ = render_events("r", events)
    assert "汇总分析" in html


def test_render_markdown_rendered_to_html():
    events = [
        PushEvent(
            task_name="T",
            result_type="per_item",
            source_name="S",
            content="# 标题\n\n**加粗**\n\n- 项1\n- 项2",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
    ]
    _, html, _, _ = render_events("r", events)
    assert "<h1>标题</h1>" in html
    assert "<strong>加粗</strong>" in html
    assert "<ul>" in html
    assert "<li>项1</li>" in html
    assert "**加粗**" not in html  # 不出现原生标记
    assert "# 标题" not in html  # 不出现原生标记


def test_render_markdown_table_to_html_table():
    events = [
        PushEvent(
            task_name="T",
            result_type="per_item",
            source_name="S",
            content="| A | B |\n|---|---|\n| 1 | 2 |",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
    ]
    _, html, _, _ = render_events("r", events)
    assert "<table>" in html
    assert "<th>A</th>" in html


def test_render_per_item_includes_file_and_article_info():
    events = [
        PushEvent(
            task_name="T",
            result_type="per_item",
            source_name="S",
            content="c",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            item_title="report.pdf",
            file_path="/data/gs/report.pdf",
            author="张三",
            author_affiliation="高盛",
            article_published_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            page_count=12,
        )
    ]
    _, html, text, _ = render_events("r", events)
    assert "report.pdf" in html
    assert "/data/gs/report.pdf" in html
    assert "张三" in html
    assert "高盛" in html
    assert "12" in html
    assert "report.pdf" in text


def test_render_per_item_omits_empty_fields():
    events = [
        PushEvent(
            task_name="T",
            result_type="per_item",
            source_name="S",
            content="c",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            item_title="report.pdf",
        )  # 其余字段为 None
    ]
    _, html, _, _ = render_events("r", events)
    assert "report.pdf" in html
    assert "作者" not in html  # 空字段不显示
    assert "页数" not in html


def test_render_aggregate_no_file_or_article_info():
    events = [
        PushEvent(
            task_name="T",
            result_type="aggregate",
            source_name="S",
            content="c",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            item_title="should-not-show",
        )
    ]
    _, html, _, _ = render_events("r", events)
    assert "文件名" not in html
    assert "作者" not in html
    assert "should-not-show" not in html


def test_render_multiple_events_separate_cards():
    events = [
        PushEvent(
            task_name="T1", result_type="per_item", source_name="S", content="c1",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        ),
        PushEvent(
            task_name="T2", result_type="per_item", source_name="S", content="c2",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        ),
    ]
    _, html, _, _ = render_events("r", events)
    assert "T1" in html and "T2" in html
    assert "c1" in html and "c2" in html


def test_render_per_item_with_figures_inserts_cid_imgs():
    events = [
        PushEvent(
            task_name="T",
            result_type="per_item",
            source_name="S",
            content="c",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            figures=[_fig("fig-1-0@isas", 1), _fig("fig-1-1@isas", 1)],
        )
    ]
    _, html, _, inline_images = render_events("r", events)
    assert 'src="cid:fig-1-0@isas"' in html
    assert 'src="cid:fig-1-1@isas"' in html
    assert len(inline_images) == 2
    assert [img.cid for img in inline_images] == ["fig-1-0@isas", "fig-1-1@isas"]


def test_render_per_item_without_figures_has_no_img():
    events = [
        PushEvent(
            task_name="T",
            result_type="per_item",
            source_name="S",
            content="c",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )
    ]
    _, html, _, inline_images = render_events("r", events)
    assert "<img" not in html
    assert inline_images == []


def test_render_aggregate_ignores_figures():
    events = [
        PushEvent(
            task_name="T",
            result_type="aggregate",
            source_name="S",
            content="c",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            figures=[_fig("fig-9-0@isas", 9)],
        )
    ]
    _, html, _, inline_images = render_events("r", events)
    assert "<img" not in html  # aggregate 不内嵌图表
    assert inline_images == []


def test_render_multiple_events_aggregate_inline_cids_unique():
    events = [
        PushEvent(
            task_name="T1", result_type="per_item", source_name="S", content="c1",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            figures=[_fig("fig-1-0@isas", 1), _fig("fig-1-1@isas", 1)],
        ),
        PushEvent(
            task_name="T2", result_type="per_item", source_name="S", content="c2",
            created_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
            figures=[_fig("fig-2-0@isas", 2)],
        ),
    ]
    _, html, _, inline_images = render_events("r", events)
    cids = [img.cid for img in inline_images]
    assert len(cids) == 3
    assert len(set(cids)) == 3  # CID 唯一
    assert all(f'src="cid:{c}"' in html for c in cids)
