"""Scheduled-job endpoints: CRUD, toggle, run-now."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..core.timeutil import utcnow
from ..models.analysis import AnalysisTask
from ..models.scheduled_job import ScheduledJob
from ..models.task import TaskRun
from ..models.user import User
from ..schemas.scheduled_job import (
    ScheduledJobCreate,
    ScheduledJobOut,
    ScheduledJobUpdate,
)
from ..services import worker
from ..services.analysis import run_analysis
from ..services import scheduler as sched_svc

router = APIRouter(prefix="/api/scheduled-jobs", tags=["定时任务"])


def _validate_fields(
    mode: str | None,
    trigger_type: str | None,
    cron_expr: str | None,
    interval_seconds: int | None,
) -> None:
    """Validate the (possibly merged) field values.

    ``None`` for ``mode``/``trigger_type`` means "unchanged" (update case) and is
    allowed; a present ``trigger_type`` is validated together with its required
    companion field (``cron_expr`` / ``interval_seconds``).
    """
    if mode is not None and mode not in ("full", "incremental"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="mode 必须是 full 或 incremental")
    if trigger_type is not None and trigger_type not in ("cron", "interval"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="trigger_type 必须是 cron 或 interval")
    if trigger_type == "cron" and not cron_expr:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 模式必须填写 cron_expr")
    if trigger_type == "interval" and (not interval_seconds or interval_seconds <= 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="interval 模式必须填写大于 0 的间隔秒数")
    if trigger_type == "cron" and cron_expr:
        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(cron_expr)
        except Exception:  # noqa: BLE001  (any parse error -> 400)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 表达式不合法")


def _out(sj: ScheduledJob) -> ScheduledJobOut:
    return ScheduledJobOut.model_validate(sj)


@router.get("", response_model=list[ScheduledJobOut])
def list_jobs(
    task_id: int | None = Query(None),
    enabled: bool | None = Query(None),
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    q = select(ScheduledJob).order_by(ScheduledJob.id.desc())
    if task_id is not None:
        q = q.where(ScheduledJob.task_id == task_id)
    if enabled is not None:
        q = q.where(ScheduledJob.enabled.is_(enabled))
    return [_out(sj) for sj in db.scalars(q).all()]


@router.post("", response_model=ScheduledJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    req: ScheduledJobCreate,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    if db.get(AnalysisTask, req.task_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="分析任务不存在")
    _validate_fields(req.mode, req.trigger_type, req.cron_expr, req.interval_seconds)
    sj = ScheduledJob(
        task_id=req.task_id,
        name=req.name,
        mode=req.mode,
        trigger_type=req.trigger_type,
        cron_expr=req.cron_expr,
        interval_seconds=req.interval_seconds,
        enabled=req.enabled,
    )
    db.add(sj)
    db.commit()
    db.refresh(sj)
    sched_svc.add_scheduled_job(sj)
    db.refresh(sj)
    return _out(sj)


@router.put("/{job_id}", response_model=ScheduledJobOut)
def update_job(
    job_id: int,
    req: ScheduledJobUpdate,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    # 跟进点2: 基于合并后的完整字段做校验(现有 sj 值 + req 的非 None 覆盖),
    # 否则只改 trigger_type 却未传 cron_expr 会误报缺失。
    merged_mode = req.mode if req.mode is not None else sj.mode
    merged_tt = req.trigger_type if req.trigger_type is not None else sj.trigger_type
    merged_cron = req.cron_expr if req.cron_expr is not None else sj.cron_expr
    merged_int = (
        req.interval_seconds if req.interval_seconds is not None else sj.interval_seconds
    )
    _validate_fields(merged_mode, merged_tt, merged_cron, merged_int)
    for f in ("name", "mode", "trigger_type", "cron_expr", "interval_seconds", "enabled"):
        v = getattr(req, f)
        if v is not None:
            setattr(sj, f, v)
    db.commit()
    db.refresh(sj)
    sched_svc.reschedule_scheduled_job(sj)
    db.refresh(sj)
    return _out(sj)


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    sched_svc.remove_scheduled_job(job_id)
    db.delete(sj)
    db.commit()
    return {"detail": "已删除"}


@router.post("/{job_id}/toggle", response_model=ScheduledJobOut)
def toggle_job(
    job_id: int,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    sj.enabled = not sj.enabled
    db.commit()
    db.refresh(sj)
    if sj.enabled:
        sched_svc.add_scheduled_job(sj)
    else:
        sched_svc.remove_scheduled_job(sj.id)
    db.refresh(sj)
    return _out(sj)


@router.post("/{job_id}/run")
def run_job_now(
    job_id: int,
    _: User = Depends(require_page("scheduled_jobs")),
    db: Session = Depends(get_db),
):
    sj = db.get(ScheduledJob, job_id)
    if sj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    task = db.get(AnalysisTask, sj.task_id)
    if task is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="关联分析任务不存在")
    run = TaskRun(
        kind="analysis",
        ref_id=task.id,
        ref_name=task.name,
        mode=sj.mode,
        status="pending",
        scheduled_job_id=sj.id,
    )
    db.add(run)
    sj.last_run_at = utcnow()
    sj.last_run_status = "running"
    db.commit()
    db.refresh(run)
    worker.submit(run_analysis, run.id, task.id, sj.mode)
    return {"run_id": run.id, "status": "pending"}
