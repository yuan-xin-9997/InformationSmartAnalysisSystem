"""Render analysis-result events into email HTML + plain-text bodies.

Decoupled from the ORM: the push service builds :class:`PushEvent` instances
(with task/source names and item metadata already resolved) and passes them
here. Markdown content is rendered to HTML via ``mistune`` (``escape=True``
escapes raw HTML tags for email safety).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

import mistune

from ...core.timeutil import format_beijing

_TYPE_LABELS = {"per_item": "逐条分析", "aggregate": "汇总分析"}

_md = mistune.create_markdown(
    escape=True, plugins=["table", "strikethrough", "task_lists", "url"]
)


@dataclass
class PushEvent:
    """A single analysis result prepared for rendering."""

    task_name: str
    result_type: str  # per_item | aggregate
    source_name: str
    content: str
    created_at: datetime
    # per_item 事件填充；aggregate 留空
    item_title: str | None = None
    file_path: str | None = None
    author: str | None = None
    author_affiliation: str | None = None
    article_published_at: datetime | None = None
    page_count: int | None = None


def _label(result_type: str) -> str:
    return _TYPE_LABELS.get(result_type, result_type)


def _nonempty(items: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    return [(k, v) for k, v in items if v not in (None, "")]


def _meta_pairs(e: PushEvent) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (file_kv, article_kv) for a per_item event; empty for aggregate."""
    if e.result_type != "per_item":
        return [], []
    file_kv = _nonempty([("文件名", e.item_title), ("文件路径", e.file_path)])
    article_kv = _nonempty(
        [
            ("作者", e.author),
            ("作者单位", e.author_affiliation),
            (
                "发布时间",
                format_beijing(e.article_published_at) if e.article_published_at else None,
            ),
            ("页数", f"{e.page_count} 页" if e.page_count is not None else None),
        ]
    )
    return file_kv, article_kv


def _meta_rows_html(e: PushEvent) -> str:
    file_kv, article_kv = _meta_pairs(e)
    if not file_kv and not article_kv:
        return ""
    parts: list[str] = []
    if file_kv:
        parts.append("文件：" + " ｜ ".join(f"{k}：{escape(v)}" for k, v in file_kv))
    if article_kv:
        parts.append("文章：" + " ｜ ".join(f"{k}：{escape(v)}" for k, v in article_kv))
    return (
        '<tr><td style="padding:8px 12px;border-bottom:1px solid #eee;'
        'font-size:13px;color:#444;line-height:1.7;">'
        + "<br/>".join(parts)
        + "</td></tr>"
    )


def _meta_lines_text(e: PushEvent) -> list[str]:
    file_kv, article_kv = _meta_pairs(e)
    lines: list[str] = []
    for k, v in file_kv:
        lines.append(f"  {k}: {v}")
    for k, v in article_kv:
        lines.append(f"  {k}: {v}")
    return lines


def _event_html(e: PushEvent) -> str:
    time_str = escape(format_beijing(e.created_at) or "")
    header = (
        '<tr><td style="background:#f5f7fa;padding:8px 12px;border-bottom:1px solid #ddd;">'
        f"<strong>{escape(e.task_name)}</strong>"
        f'<span style="color:#666;margin-left:8px;">{escape(_label(e.result_type))}</span>'
        f'<span style="color:#666;margin-left:8px;">来源：{escape(e.source_name)}</span>'
        f'<span style="color:#999;margin-left:8px;float:right;">{time_str}</span>'
        "</td></tr>"
    )
    body = '<tr><td style="padding:8px 12px;">' + _md(e.content or "") + "</td></tr>"
    return (
        '<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
        'width:100%;margin-bottom:16px;border:1px solid #ddd;border-radius:4px;">'
        + header
        + _meta_rows_html(e)
        + body
        + "</table>"
    )


def render_events(rule_name: str, events: list[PushEvent]) -> tuple[str, str, str]:
    """Return ``(subject, html, text)`` for a batch of events."""
    n = len(events)
    subject = f"【信息分析】{rule_name} - {n}条新事件"

    html = (
        '<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:14px;color:#333;">'
        f'<h3 style="margin:0 0 12px;">{escape(rule_name)}：{n} 条新分析事件</h3>'
        + "".join(_event_html(e) for e in events)
        + "</div>"
    )

    lines = [f"{rule_name}：{n} 条新分析事件", ""]
    for i, e in enumerate(events, 1):
        lines.append(
            f"#{i} [{_label(e.result_type)}] {e.task_name} / "
            f"{e.source_name} / {format_beijing(e.created_at)}"
        )
        lines.extend(_meta_lines_text(e))
        lines.append("")
        lines.append(e.content or "")
        lines.append("")
    text = "\n".join(lines)

    return subject, html, text
