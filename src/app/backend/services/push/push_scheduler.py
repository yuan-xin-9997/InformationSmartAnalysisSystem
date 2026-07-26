"""Scheduled-push: registers ``scheduled`` push rules on the shared APScheduler.

Reuses the BackgroundScheduler owned by ``services.scheduler`` (one process-wide
scheduler). Push jobs use the id namespace ``push-{rule_id}`` so they never
collide with analysis scheduled-job ids. CRUD on push rules syncs the
scheduler; ``start_push_scheduler`` loads enabled rules at startup.

When ``scheduler.enabled=false`` the shared scheduler is never created, so
scheduled push is unavailable (on_run and manual triggers are unaffected).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from ...core.config import settings
from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...models.push import PushRule
from .. import scheduler as sched_svc
from .. import worker
from .service import run_push

_logger = get_logger("push.scheduler")


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone_display)


def _job_id(rule_id: int) -> str:
    return f"push-{rule_id}"


def _build_trigger(rule: PushRule):
    if rule.cron_expr:
        return CronTrigger.from_crontab(rule.cron_expr, timezone=_tz())
    if rule.interval_seconds and rule.interval_seconds > 0:
        return IntervalTrigger(seconds=rule.interval_seconds, timezone=_tz())
    raise ValueError("scheduled 推送规则必须填写 cron_expr 或大于 0 的 interval_seconds")


def _fire(rule_id: int) -> None:
    """Scheduler callback: submit a scheduled push."""
    worker.submit(run_push, rule_id, "scheduled")


def _add_job(rule: PushRule) -> None:
    s = sched_svc.get_scheduler()
    if s is None:
        return
    s.add_job(
        _fire,
        trigger=_build_trigger(rule),
        args=[rule.id],
        id=_job_id(rule.id),
        max_instances=settings.scheduler_max_instances,
        coalesce=settings.scheduler_coalesce,
        misfire_grace_time=settings.scheduler_misfire_grace_seconds,
        replace_existing=True,
    )


def add_push_job(rule: PushRule) -> None:
    """Register a push rule on the scheduler if enabled and scheduled."""
    s = sched_svc.get_scheduler()
    if s is not None and rule.enabled and rule.trigger_mode == "scheduled":
        _add_job(rule)


def remove_push_job(rule_id: int) -> None:
    s = sched_svc.get_scheduler()
    if s is None:
        return
    try:
        s.remove_job(_job_id(rule_id))
    except Exception:  # noqa: BLE001  (job may not be registered if disabled/non-scheduled)
        pass


def reschedule_push_job(rule: PushRule) -> None:
    remove_push_job(rule.id)
    add_push_job(rule)


def start_push_scheduler() -> None:
    """Load enabled scheduled push rules into the shared scheduler at startup."""
    s = sched_svc.get_scheduler()
    if s is None:
        _logger.info("定时调度器未启用，跳过推送定时规则加载")
        return
    with SessionLocal() as db:
        rules = db.scalars(
            select(PushRule).where(
                PushRule.enabled.is_(True), PushRule.trigger_mode == "scheduled"
            )
        ).all()
        for rule in rules:
            try:
                _add_job(rule)
            except Exception:  # noqa: BLE001
                _logger.exception("加载推送定时规则 %s 失败", rule.id)
    _logger.info("推送定时调度已启动，加载 %d 个已启用规则", len(rules))
