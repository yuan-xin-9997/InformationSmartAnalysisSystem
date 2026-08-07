"""Push service: incremental delivery of analysis results to email.

``run_push`` is the single execution path for all three trigger modes. It runs
in the worker (own DB session): resolve SMTP -> collect incremental events by
watermark -> render+send in batches -> advance the watermark after each
successful batch -> write a ``PushRun`` history row. A failed batch does NOT
advance the watermark, so the next run retries from that batch.

Each batch's rendered email (subject + HTML with charts CID-embedded) is
retained on the ``PushRun`` as a browser-previewable HTML (charts converted to
``data:`` URLs) so the push history can preview what was actually sent.

``on_analysis_completed`` is the hook called by the analysis engine after a
successful run; it submits ``run_push`` for every matching ``on_run`` rule.
The hook swallows its own errors so it can never affect the analysis result.
"""
from __future__ import annotations

import base64
import re
from html import escape
from typing import Any

from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...core.timeutil import utcnow
from ...models.analysis import AnalysisResult, AnalysisTask
from ...models.info_source import InfoItem, InfoSource
from ...models.push import PushRule, PushRun
from .. import worker
from .attachments import Attachment, InlineImage, collect_push_media
from .channels import get_channel
from .render import PushEvent, render_events
from .smtp_config import SmtpConfigError, resolve_smtp_config

_logger = get_logger("push")


def _collect_events(db, rule: PushRule) -> list[AnalysisResult]:
    q = db.query(AnalysisResult).filter(
        AnalysisResult.task_id == rule.task_id,
        AnalysisResult.result_type.in_(rule.event_types or []),
    )
    if rule.last_pushed_result_id is not None:
        q = q.filter(AnalysisResult.id > rule.last_pushed_result_id)
    return q.order_by(AnalysisResult.id.asc()).all()


def _to_push_event(db, r: AnalysisResult, inline_by_item: dict | None = None) -> PushEvent:
    inline_by_item = inline_by_item or {}
    task = db.get(AnalysisTask, r.task_id)
    source = db.get(InfoSource, r.source_id) if r.source_id else None
    item = db.get(InfoItem, r.info_item_id) if r.info_item_id else None
    figures = inline_by_item.get(r.info_item_id, []) if r.info_item_id else []
    return PushEvent(
        task_name=task.name if task else f"任务#{r.task_id}",
        result_type=r.result_type,
        source_name=source.name if source else "(无)",
        content=r.content,
        created_at=r.created_at,
        item_title=item.title if item else None,
        file_path=item.external_id if item else None,
        author=item.author if item else None,
        author_affiliation=item.author_affiliation if item else None,
        article_published_at=item.article_published_at if item else None,
        page_count=item.page_count if item else None,
        figures=figures,
    )


def _build_attachment_summary(
    attachments: list[Attachment], inline_figures: list[InlineImage]
) -> list[dict]:
    """附件清单：图表（来自内联图，每张一次）+ 原文件（非图表的附件）。"""
    fig_names = {img.filename for img in inline_figures}
    summary: list[dict] = [{"filename": img.filename, "kind": "figure"} for img in inline_figures]
    summary += [
        {"filename": a.filename, "kind": "file"}
        for a in attachments
        if a.filename not in fig_names
    ]
    return summary


def _cid_to_data_url(html: str, inline_images: list[InlineImage]) -> str:
    """把 HTML 中的 ``cid:<cid>`` 替换为 ``data:<mime>;base64,<data>``，生成浏览器可渲染 HTML。"""
    if not inline_images:
        return html
    by_cid = {img.cid: img for img in inline_images}

    def _repl(m: re.Match) -> str:
        img = by_cid.get(m.group(1))
        if img is None:
            return m.group(0)
        b64 = base64.b64encode(img.data).decode("ascii")
        return f"data:{img.mime};base64,{b64}"

    return re.sub(r"cid:([^\"'\s>]+)", _repl, html)


def _merge_preview_parts(
    parts: list[tuple[str | None, str | None, list | None]],
) -> tuple[str | None, str | None, list | None]:
    """合并多批邮件的预览内容：单批直接返回；多批按序拼接并加分隔标题。"""
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0][0], parts[0][1], parts[0][2]
    n = len(parts)
    merged_html: list[str] = []
    merged_att: list = []
    for i, (subject, html, att) in enumerate(parts, 1):
        merged_html.append(
            f'<h4 style="margin:16px 0 8px;border-top:1px solid #ddd;padding-top:8px;">'
            f"第 {i} 封 / 共 {n} 封：{escape(subject or '')}</h4>"
            + (html or "")
        )
        if att:
            merged_att.extend(att)
    return parts[0][0], "".join(merged_html), merged_att


def _log_run(
    db,
    rule: PushRule,
    trigger_mode: str,
    count: int,
    status: str,
    error: str | None,
    started_at: Any | None = None,
    subject: str | None = None,
    email_html: str | None = None,
    attachment_summary: list | None = None,
) -> None:
    db.add(
        PushRun(
            rule_id=rule.id,
            trigger_mode=trigger_mode,
            recipients=list(rule.recipients or []),
            event_count=count,
            status=status,
            error=error,
            subject=subject,
            email_html=email_html,
            attachment_summary=attachment_summary,
            started_at=started_at,
            finished_at=utcnow(),
        )
    )
    db.commit()


def run_push(rule_id: int, trigger_mode: str) -> None:
    with SessionLocal() as db:
        rule = db.get(PushRule, rule_id)
        if rule is None or not rule.enabled:
            return

        channel = get_channel(rule.channel)
        if channel is None:
            _log_run(db, rule, trigger_mode, 0, "failed", f"未知推送渠道: {rule.channel}")
            return

        try:
            cfg = resolve_smtp_config(db)
        except SmtpConfigError as e:
            _log_run(db, rule, trigger_mode, 0, "failed", str(e))
            return

        results = _collect_events(db, rule)
        if not results:
            _log_run(db, rule, trigger_mode, 0, "no_new", None)
            return

        recipients = list(rule.recipients or [])
        batch_size = rule.max_events_per_email or 50
        started_at = utcnow()
        total = 0
        preview_parts: list[tuple[str | None, str | None, list | None]] = []
        try:
            for i in range(0, len(results), batch_size):
                batch = results[i : i + batch_size]
                attachments, inline_figures = collect_push_media(db, batch)
                inline_by_item: dict[int, list[InlineImage]] = {}
                for img in inline_figures:
                    inline_by_item.setdefault(img.item_id, []).append(img)
                events = [_to_push_event(db, r, inline_by_item) for r in batch]
                subject, html, text, inline_images = render_events(rule.name, events)
                channel.send(
                    cfg, recipients, subject, html, text,
                    attachments=attachments, inline_images=inline_images,
                )
                preview_html = _cid_to_data_url(html, inline_images)
                att_summary = _build_attachment_summary(attachments, inline_figures)
                preview_parts.append((subject, preview_html, att_summary))
                # 每批发送成功后立即推进水位线并提交
                rule.last_pushed_result_id = batch[-1].id
                db.commit()
                total += len(batch)
            email_subject, email_html, attachment_summary = _merge_preview_parts(preview_parts)
            _log_run(
                db, rule, trigger_mode, total, "succeeded", None, started_at,
                email_subject, email_html, attachment_summary,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("推送规则 [%s] 发送失败", rule.name)
            # 已发出的批次留存预览内容（失败记录若已发 ≥1 封仍可预览）
            email_subject, email_html, attachment_summary = _merge_preview_parts(preview_parts)
            _log_run(
                db, rule, trigger_mode, total, "failed", str(exc), started_at,
                email_subject, email_html, attachment_summary,
            )


def on_analysis_completed(task_id: int) -> None:
    """分析任务成功完成后：为匹配的 on_run 推送配置触发增量推送（1:1，按 task_id）。

    异常隔离：任何错误仅记日志，不得影响已成功的分析结果。
    """
    try:
        with SessionLocal() as db:
            rules = (
                db.query(PushRule)
                .filter(
                    PushRule.enabled.is_(True),
                    PushRule.trigger_mode == "on_run",
                    PushRule.task_id == task_id,
                )
                .all()
            )
            ids = [r.id for r in rules]
        for rid in ids:
            worker.submit(run_push, rid, "on_run")
    except Exception:  # noqa: BLE001
        _logger.exception("on_analysis_completed 触发推送失败 task_id=%s", task_id)
