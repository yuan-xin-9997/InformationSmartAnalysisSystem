"""Push service: incremental delivery of analysis results to email.

``run_push`` is the single execution path for all three trigger modes. It runs
in the worker (own DB session): resolve SMTP -> collect incremental events by
watermark -> render+send in batches -> advance the watermark after each
successful batch -> write a ``PushRun`` history row. A failed batch does NOT
advance the watermark, so the next run retries from that batch.

``on_analysis_completed`` is the hook called by the analysis engine after a
successful run; it submits ``run_push`` for every matching ``on_run`` rule.
The hook swallows its own errors so it can never affect the analysis result.
"""
from __future__ import annotations

from typing import Any

from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...core.timeutil import utcnow
from ...models.analysis import AnalysisResult, AnalysisTask
from ...models.info_source import InfoItem, InfoSource
from ...models.push import PushRule, PushRun
from .. import worker
from .attachments import collect_attachments
from .channels import get_channel
from .render import PushEvent, render_events
from .smtp_config import SmtpConfigError, resolve_smtp_config

_logger = get_logger("push")


def _collect_events(db, rule: PushRule) -> list[AnalysisResult]:
    q = db.query(AnalysisResult).filter(
        AnalysisResult.task_id.in_(rule.task_ids or []),
        AnalysisResult.result_type.in_(rule.event_types or []),
    )
    if rule.last_pushed_result_id is not None:
        q = q.filter(AnalysisResult.id > rule.last_pushed_result_id)
    return q.order_by(AnalysisResult.id.asc()).all()


def _to_push_event(db, r: AnalysisResult) -> PushEvent:
    task = db.get(AnalysisTask, r.task_id)
    source = db.get(InfoSource, r.source_id) if r.source_id else None
    item = db.get(InfoItem, r.info_item_id) if r.info_item_id else None
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
    )


def _log_run(
    db,
    rule: PushRule,
    trigger_mode: str,
    count: int,
    status: str,
    error: str | None,
    started_at: Any | None = None,
) -> None:
    db.add(
        PushRun(
            rule_id=rule.id,
            trigger_mode=trigger_mode,
            recipients=list(rule.recipients or []),
            event_count=count,
            status=status,
            error=error,
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
        try:
            for i in range(0, len(results), batch_size):
                batch = results[i : i + batch_size]
                events = [_to_push_event(db, r) for r in batch]
                subject, html, text = render_events(rule.name, events)
                attachments = collect_attachments(db, batch)
                channel.send(cfg, recipients, subject, html, text, attachments=attachments)
                # 每批发送成功后立即推进水位线并提交
                rule.last_pushed_result_id = batch[-1].id
                db.commit()
                total += len(batch)
            _log_run(db, rule, trigger_mode, total, "succeeded", None, started_at)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("推送规则 [%s] 发送失败", rule.name)
            _log_run(db, rule, trigger_mode, total, "failed", str(exc), started_at)


def on_analysis_completed(task_id: int) -> None:
    """分析任务成功完成后：为匹配的 on_run 规则触发增量推送。

    异常隔离：任何错误仅记日志，不得影响已成功的分析结果。
    """
    try:
        with SessionLocal() as db:
            rules = (
                db.query(PushRule)
                .filter(PushRule.enabled.is_(True), PushRule.trigger_mode == "on_run")
                .all()
            )
            ids = [r.id for r in rules if task_id in (r.task_ids or [])]
        for rid in ids:
            worker.submit(run_push, rid, "on_run")
    except Exception:  # noqa: BLE001
        _logger.exception("on_analysis_completed 触发推送失败 task_id=%s", task_id)
