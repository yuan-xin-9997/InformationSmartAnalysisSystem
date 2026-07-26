"""Process-wide APScheduler that auto-triggers analysis tasks on schedule.

Config lives in the ``scheduled_jobs`` table (managed via API/UI). On startup
we load enabled jobs into an in-memory BackgroundScheduler; CRUD operations
sync the scheduler so DB and memory stay consistent. Firing a job creates a
``TaskRun`` and reuses the existing ``worker.submit(run_analysis, ...)`` path.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from ..core.config import settings
from ..core.database import SessionLocal
from ..core.logging import get_logger
from ..core.timeutil import utcnow
from ..models.analysis import AnalysisTask
from ..models.scheduled_job import ScheduledJob
from ..models.task import TaskRun
from . import worker
from .analysis import run_analysis

_logger = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone_display)


def _build_trigger(job: ScheduledJob):
    if job.trigger_type == "cron":
        if not job.cron_expr:
            raise ValueError("cron 模式必须填写 cron_expr")
        return CronTrigger.from_crontab(job.cron_expr, timezone=_tz())
    if job.trigger_type == "interval":
        if not job.interval_seconds or job.interval_seconds <= 0:
            raise ValueError("interval 模式必须填写大于 0 的间隔秒数")
        return IntervalTrigger(seconds=job.interval_seconds, timezone=_tz())
    raise ValueError(f"未知触发类型: {job.trigger_type}")


def _job_id(job_id: int) -> str:
    return str(job_id)


def _sync_next_run(job_id: int) -> None:
    """Persist the scheduler's next_run_time back to the DB for display."""
    if _scheduler is None:
        return
    job = _scheduler.get_job(_job_id(job_id))
    nxt: datetime | None = getattr(job, "next_run_time", None) if job else None
    with SessionLocal() as db:
        sj = db.get(ScheduledJob, job_id)
        if sj:
            sj.next_run_at = nxt
            db.commit()


def _fire(job_id: int) -> None:
    """Scheduler callback: create a TaskRun and submit run_analysis."""
    with SessionLocal() as db:
        sj = db.get(ScheduledJob, job_id)
        if sj is None or not sj.enabled:
            return
        task = db.get(AnalysisTask, sj.task_id)
        if task is None:
            _logger.warning("定时任务 %s 关联分析任务不存在", job_id)
            return
        run = TaskRun(
            kind="analysis",
            ref_id=task.id,
            ref_name=task.name,
            mode=sj.mode,
            status="pending",
            scheduled_job_id=job_id,
        )
        db.add(run)
        sj.last_run_at = utcnow()
        sj.last_run_status = "running"
        db.commit()
        db.refresh(run)
        run_id, task_id, mode = run.id, task.id, sj.mode
    worker.submit(run_analysis, run_id, task_id, mode)
    _sync_next_run(job_id)


def _add_job(sj: ScheduledJob) -> None:
    if _scheduler is None:
        return
    _scheduler.add_job(
        _fire,
        trigger=_build_trigger(sj),
        args=[sj.id],
        id=_job_id(sj.id),
        max_instances=settings.scheduler_max_instances,
        coalesce=settings.scheduler_coalesce,
        misfire_grace_time=settings.scheduler_misfire_grace_seconds,
        replace_existing=True,
    )


def add_scheduled_job(sj: ScheduledJob) -> None:
    if _scheduler is not None and sj.enabled:
        _add_job(sj)
        _sync_next_run(sj.id)


def remove_scheduled_job(job_id: int) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_job_id(job_id))
    except Exception:  # noqa: BLE001  (job may not be in scheduler if disabled)
        pass


def reschedule_scheduled_job(sj: ScheduledJob) -> None:
    remove_scheduled_job(sj.id)
    add_scheduled_job(sj)


def start_scheduler() -> None:
    global _scheduler
    if not settings.scheduler_enabled:
        _logger.info("定时任务调度器已禁用 (scheduler.enabled=false)")
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=_tz(),
    )
    with SessionLocal() as db:
        jobs = db.scalars(select(ScheduledJob).where(ScheduledJob.enabled.is_(True))).all()
        for sj in jobs:
            try:
                _add_job(sj)
            except Exception:  # noqa: BLE001
                _logger.exception("加载定时任务 %s 失败", sj.id)
    _scheduler.start()
    _logger.info("定时任务调度器已启动,加载 %d 个已启用任务", len(jobs))


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
