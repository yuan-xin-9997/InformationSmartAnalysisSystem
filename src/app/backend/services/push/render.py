"""Render analysis-result events into email HTML + plain-text bodies.

Decoupled from the ORM: the push service builds :class:`PushEvent` instances
(with task/source names already resolved) and passes them here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape

from ...core.timeutil import format_beijing

_TYPE_LABELS = {"per_item": "逐条分析", "aggregate": "汇总分析"}


@dataclass
class PushEvent:
    """A single analysis result prepared for rendering."""

    task_name: str
    result_type: str  # per_item | aggregate
    source_name: str
    content: str
    created_at: datetime


def _label(result_type: str) -> str:
    return _TYPE_LABELS.get(result_type, result_type)


def render_events(rule_name: str, events: list[PushEvent]) -> tuple[str, str, str]:
    """Return ``(subject, html, text)`` for a batch of events."""
    n = len(events)
    subject = f"【信息分析】{rule_name} - {n}条新事件"

    rows: list[str] = []
    for i, e in enumerate(events, 1):
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{escape(e.task_name)}</td>"
            f"<td>{_label(e.result_type)}</td>"
            f"<td>{escape(e.source_name)}</td>"
            f"<td>{escape(format_beijing(e.created_at) or '')}</td>"
            f"<td><pre>{escape(e.content)}</pre></td>"
            "</tr>"
        )
    html = (
        f"<h3>{escape(rule_name)}：{n} 条新分析事件</h3>"
        '<table border="1" cellpadding="6" cellspacing="0" '
        'style="border-collapse:collapse;">'
        "<tr><th>#</th><th>任务</th><th>类型</th><th>来源</th>"
        "<th>时间(北京)</th><th>内容</th></tr>"
        + "".join(rows)
        + "</table>"
    )

    lines = [f"{rule_name}：{n} 条新分析事件", ""]
    for i, e in enumerate(events, 1):
        lines.append(
            f"#{i} [{_label(e.result_type)}] {e.task_name} / "
            f"{e.source_name} / {format_beijing(e.created_at)}"
        )
        lines.append(e.content)
        lines.append("")
    text = "\n".join(lines)

    return subject, html, text
