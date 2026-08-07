"""Analysis-task endpoints: CRUD, bind sources, trigger analysis, view results.

Consolidated (consolidate-task-analysis-page): each task also owns at most one
1:1 scheduled-analysis config and one 1:1 push config, managed through the task
edit dialog. ``PUT /api/analysis-tasks/{id}`` upserts/deletes them in one
transaction; list/detail responses carry the full ``schedule``/``push`` configs.
"""
from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..core.timeutil import utcnow
from ..models.analysis import AnalysisResult, AnalysisTask, TaskSource
from ..models.info_source import InfoItem, InfoItemFigure, InfoSource
from ..models.push import PushRule, PushRun
from ..models.scheduled_job import ScheduledJob
from ..models.task import TaskRun
from ..models.user import User
from ..schemas.analysis import (
    AnalysisResultOut,
    AnalysisTaskCreate,
    AnalysisTaskDetailOut,
    AnalysisTaskUpdate,
    PushConfigBase,
    PushConfigOut,
    RunAnalysisRequest,
    ScheduleConfigBase,
    ScheduleConfigOut,
    TaskSourceOut,
)
from ..schemas.info_source import InfoItemFigureOut, SourceFileOut
from ..schemas.push import PushRunOut, PushRunPreviewOut
from ..services import worker
from ..services.analysis import run_analysis
from ..services import scheduler as sched_svc
from ..services.push.push_scheduler import reschedule_push_job, remove_push_job
from ..services.push.service import run_push

router = APIRouter(prefix="/api/analysis-tasks", tags=["分析任务"])


# ---------- sub-config helpers (1:1 schedule / push) ----------


def _build_sources(task: AnalysisTask) -> list[TaskSourceOut]:
    out: list[TaskSourceOut] = []
    for ts in task.task_sources:
        src = ts.source
        out.append(
            TaskSourceOut(
                source_id=ts.source_id,
                source_name=src.name if src else "(已删除)",
                source_type=src.type if src else "",
                source_status=src.status if src else "error",
                item_count=src.item_count if src else 0,
                last_analyzed_item_id=ts.last_analyzed_item_id,
                last_analyzed_at=ts.last_analyzed_at,
            )
        )
    return out


def _attach_sub_configs(db: Session, task: AnalysisTask, detail: AnalysisTaskDetailOut) -> None:
    """Populate the task's 1:1 schedule/push configs on the response schema."""
    sj = db.scalar(select(ScheduledJob).where(ScheduledJob.task_id == task.id))
    detail.schedule = ScheduleConfigOut.model_validate(sj) if sj else None
    pr = db.scalar(select(PushRule).where(PushRule.task_id == task.id))
    detail.push = PushConfigOut.model_validate(pr) if pr else None


def _attach_sub_configs_batch(
    db: Session, tasks: list[AnalysisTask], details: list[AnalysisTaskDetailOut]
) -> None:
    if not tasks:
        return
    ids = [t.id for t in tasks]
    sjs = {
        sj.task_id: sj
        for sj in db.scalars(select(ScheduledJob).where(ScheduledJob.task_id.in_(ids))).all()
    }
    prs = {
        pr.task_id: pr
        for pr in db.scalars(select(PushRule).where(PushRule.task_id.in_(ids))).all()
    }
    for task, detail in zip(tasks, details):
        sj = sjs.get(task.id)
        pr = prs.get(task.id)
        detail.schedule = ScheduleConfigOut.model_validate(sj) if sj else None
        detail.push = PushConfigOut.model_validate(pr) if pr else None


def _validate_schedule(cfg: ScheduleConfigBase) -> None:
    if cfg.mode not in ("full", "incremental"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="定时模式必须是 full 或 incremental")
    if cfg.trigger_type not in ("cron", "interval"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="触发类型必须是 cron 或 interval")
    if cfg.trigger_type == "cron":
        if not cfg.cron_expr:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 模式必须填写 cron_expr")
        try:
            CronTrigger.from_crontab(cfg.cron_expr)
        except Exception:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 表达式不合法")
    if cfg.trigger_type == "interval" and (not cfg.interval_seconds or cfg.interval_seconds <= 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="interval 模式必须填写大于 0 的间隔秒数")


def _validate_push(cfg: PushConfigBase) -> None:
    if cfg.trigger_mode not in ("on_run", "scheduled", "manual"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="trigger_mode 取值: on_run|scheduled|manual")
    if not cfg.event_types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="请选择至少一种事件类型")
    if not cfg.recipients:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="请填写至少一个收件人邮箱")
    if cfg.trigger_mode == "scheduled" and not (
        cfg.cron_expr or (cfg.interval_seconds and cfg.interval_seconds > 0)
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="scheduled 模式必须填写 cron_expr 或大于 0 的 interval_seconds"
        )
    if cfg.cron_expr:
        try:
            CronTrigger.from_crontab(cfg.cron_expr)
        except Exception:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="cron 表达式不合法")


def _upsert_schedule(db: Session, task_id: int, cfg: ScheduleConfigBase, task_name: str) -> ScheduledJob:
    sj = db.scalar(select(ScheduledJob).where(ScheduledJob.task_id == task_id))
    if sj is None:
        sj = ScheduledJob(task_id=task_id, name=f"{task_name}-定时")
        db.add(sj)
    sj.mode = cfg.mode
    sj.trigger_type = cfg.trigger_type
    sj.cron_expr = cfg.cron_expr if cfg.trigger_type == "cron" else None
    sj.interval_seconds = cfg.interval_seconds if cfg.trigger_type == "interval" else None
    sj.enabled = cfg.enabled
    return sj


def _upsert_push(db: Session, task_id: int, cfg: PushConfigBase, task_name: str) -> PushRule:
    pr = db.scalar(select(PushRule).where(PushRule.task_id == task_id))
    if pr is None:
        pr = PushRule(task_id=task_id, name=f"{task_name}-推送", channel="email")
        db.add(pr)
    pr.event_types = cfg.event_types
    pr.recipients = cfg.recipients
    pr.trigger_mode = cfg.trigger_mode
    pr.cron_expr = cfg.cron_expr
    pr.interval_seconds = cfg.interval_seconds
    pr.enabled = cfg.enabled
    pr.max_events_per_email = cfg.max_events_per_email
    return pr


def _apply_sub_configs(
    db: Session, task_id: int, task_name: str, req: AnalysisTaskCreate | AnalysisTaskUpdate
) -> dict:
    """Upsert/delete the 1:1 schedule & push configs declared on the request.

    Returns a dict of deferred scheduler-sync actions to run AFTER commit:
    ``{"schedule": ("delete", job_id) | ("upsert", sj) | None,
       "push": ("delete", rule_id) | ("upsert", pr) | None}``.
    """
    actions: dict[str, tuple | None] = {"schedule": None, "push": None}
    # Create has no delete semantics; Update distinguishes null=delete via model_fields_set.
    fields_set = getattr(req, "model_fields_set", set())
    schedule_provided = "schedule" in fields_set if isinstance(req, AnalysisTaskUpdate) else req.schedule is not None
    push_provided = "push" in fields_set if isinstance(req, AnalysisTaskUpdate) else req.push is not None

    if schedule_provided:
        if req.schedule is None:
            existing = db.scalar(select(ScheduledJob).where(ScheduledJob.task_id == task_id))
            if existing:
                actions["schedule"] = ("delete", existing.id)
                db.delete(existing)
        else:
            _validate_schedule(req.schedule)
            actions["schedule"] = ("upsert", _upsert_schedule(db, task_id, req.schedule, task_name))

    if push_provided:
        if req.push is None:
            existing = db.scalar(select(PushRule).where(PushRule.task_id == task_id))
            if existing:
                actions["push"] = ("delete", existing.id)
                db.delete(existing)
        else:
            _validate_push(req.push)
            actions["push"] = ("upsert", _upsert_push(db, task_id, req.push, task_name))
    return actions


def _sync_after_commit(db: Session, actions: dict) -> None:
    """Run deferred scheduler sync after the DB transaction commits."""
    sched_act = actions.get("schedule")
    if sched_act:
        if sched_act[0] == "delete":
            sched_svc.remove_scheduled_job(sched_act[1])
        else:
            db.refresh(sched_act[1])
            sched_svc.reschedule_scheduled_job(sched_act[1])
    push_act = actions.get("push")
    if push_act:
        if push_act[0] == "delete":
            remove_push_job(push_act[1])
        else:
            db.refresh(push_act[1])
            reschedule_push_job(push_act[1])


# ---------- task CRUD ----------


@router.get("", response_model=list[AnalysisTaskDetailOut])
def list_tasks(
    _: User = Depends(require_page("analysis_tasks")), db: Session = Depends(get_db)
):
    tasks = db.scalars(select(AnalysisTask).order_by(AnalysisTask.id.desc())).all()
    out: list[AnalysisTaskDetailOut] = []
    for task in tasks:
        detail = AnalysisTaskDetailOut.model_validate(task)
        detail.sources = _build_sources(task)
        out.append(detail)
    _attach_sub_configs_batch(db, tasks, out)
    return out


@router.post("", response_model=AnalysisTaskDetailOut, status_code=status.HTTP_201_CREATED)
def create_task(
    req: AnalysisTaskCreate,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    task = AnalysisTask(
        name=req.name, description=req.description, config=req.config or {}
    )
    for sid in req.source_ids:
        if db.get(InfoSource, sid) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"信息源不存在: {sid}"
            )
        task.task_sources.append(TaskSource(source_id=sid))
    db.add(task)
    db.flush()  # assign task.id for the 1:1 sub-config FKs
    actions = _apply_sub_configs(db, task.id, task.name, req)
    db.commit()
    db.refresh(task)
    _sync_after_commit(db, actions)
    detail = AnalysisTaskDetailOut.model_validate(task)
    detail.sources = _build_sources(task)
    _attach_sub_configs(db, task, detail)
    return detail


@router.get("/{task_id}", response_model=AnalysisTaskDetailOut)
def get_task(
    task_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    detail = AnalysisTaskDetailOut.model_validate(task)
    detail.sources = _build_sources(task)
    _attach_sub_configs(db, task, detail)
    return detail


@router.put("/{task_id}", response_model=AnalysisTaskDetailOut)
def update_task(
    task_id: int,
    req: AnalysisTaskUpdate,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    if req.name is not None:
        task.name = req.name
    if req.description is not None:
        task.description = req.description
    if req.config is not None:
        task.config = req.config
    if req.source_ids is not None:
        db.query(TaskSource).filter(TaskSource.task_id == task_id).delete()
        for sid in req.source_ids:
            if db.get(InfoSource, sid) is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"信息源不存在: {sid}"
                )
            task.task_sources.append(TaskSource(source_id=sid))
    actions = _apply_sub_configs(db, task_id, task.name, req)
    db.commit()
    db.refresh(task)
    _sync_after_commit(db, actions)
    detail = AnalysisTaskDetailOut.model_validate(task)
    detail.sources = _build_sources(task)
    _attach_sub_configs(db, task, detail)
    return detail


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    # 1:1 sub-configs: stop their scheduler jobs; ORM/DB cascade removes the rows.
    sj = db.scalar(select(ScheduledJob).where(ScheduledJob.task_id == task_id))
    if sj:
        sched_svc.remove_scheduled_job(sj.id)
    pr = db.scalar(select(PushRule).where(PushRule.task_id == task_id))
    if pr:
        remove_push_job(pr.id)
    db.delete(task)
    db.commit()
    return {"detail": "已删除"}


@router.get("/{task_id}/sources", response_model=list[TaskSourceOut])
def list_task_sources(
    task_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    return _build_sources(task)


@router.post("/{task_id}/run")
def run_task(
    task_id: int,
    req: RunAnalysisRequest,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    if req.mode not in ("full", "incremental", "custom"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode 必须是 full、incremental 或 custom",
        )
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    run_mode = "custom" if (req.mode == "custom" or (task.config or {}).get("mode") == "custom") else req.mode
    run = TaskRun(
        kind="analysis",
        ref_id=task_id,
        ref_name=task.name,
        mode=run_mode,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    worker.submit(run_analysis, run.id, task_id, req.mode)
    return {"run_id": run.id, "status": "pending"}


# ---------- 1:1 sub-config actions ----------


@router.post("/{task_id}/schedule/run")
def run_schedule_now(
    task_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    """立即执行该任务的定时分析（按其定时配置的 mode 触发一次运行）。"""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    sj = db.scalar(select(ScheduledJob).where(ScheduledJob.task_id == task_id))
    if sj is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该任务未配置定时分析")
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


@router.post("/{task_id}/push/trigger")
def trigger_push(
    task_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    """手动触发该任务的推送（按其 1:1 推送配置执行一次增量推送）。"""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    pr = db.scalar(select(PushRule).where(PushRule.task_id == task_id))
    if pr is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该任务未配置推送")
    worker.submit(run_push, pr.id, "manual")
    return {"ok": True}


@router.get("/{task_id}/push/runs", response_model=list[PushRunOut])
def list_push_runs(
    task_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    """按任务查看推送历史（该任务 1:1 推送配置的历次推送记录）。"""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分析任务不存在")
    pr = db.scalar(select(PushRule).where(PushRule.task_id == task_id))
    if pr is None:
        return []
    runs = db.scalars(
        select(PushRun).where(PushRun.rule_id == pr.id).order_by(PushRun.id.desc())
    ).all()
    return [_serialize_push_run(r) for r in runs]


def _serialize_push_run(run: PushRun) -> dict:
    """序列化 PushRun -> dict（push-email-preview-inline-figures）。

    显式计算 ``has_preview``（派生自 ``email_html``），避免 Pydantic 对
    ``@property`` 派生字段在 ``from_attributes`` 模式下的读取差异。
    """
    return {
        "id": run.id,
        "rule_id": run.rule_id,
        "trigger_mode": run.trigger_mode,
        "recipients": run.recipients,
        "event_count": run.event_count,
        "status": run.status,
        "error": run.error,
        "subject": run.subject,
        "attachment_summary": run.attachment_summary,
        "has_preview": run.has_preview,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "created_at": run.created_at,
    }


@router.get(
    "/{task_id}/push/runs/{run_id}/preview",
    response_model=PushRunPreviewOut,
)
def get_push_run_preview(
    task_id: int,
    run_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    """推送历史邮件预览（push-email-preview-inline-figures）。"""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分析任务不存在")
    pr = db.scalar(select(PushRule).where(PushRule.task_id == task_id))
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该任务未配置推送")
    run = db.get(PushRun, run_id)
    if run is None or run.rule_id != pr.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "推送记录不存在")
    if run.email_html is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该推送记录无可预览内容")
    return PushRunPreviewOut(
        subject=run.subject,
        html=run.email_html,
        attachments=run.attachment_summary,
    )


# ---------- results ----------


@router.get("/{task_id}/results", response_model=list[AnalysisResultOut])
def list_task_results(
    task_id: int,
    run_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    q = (
        select(AnalysisResult)
        .where(AnalysisResult.task_id == task_id)
        .order_by(AnalysisResult.id.desc())
        .limit(limit)
    )
    if run_id:
        q = q.where(AnalysisResult.task_run_id == run_id)
    results = db.scalars(q).all()

    item_ids = {r.info_item_id for r in results if r.info_item_id}
    items_map: dict[int, InfoItem] = {}
    figs_by_item: dict[int, list[InfoItemFigure]] = {}
    if item_ids:
        items_map = {
            it.id: it
            for it in db.scalars(
                select(InfoItem).where(InfoItem.id.in_(item_ids))
            ).all()
        }
        figs = db.scalars(
            select(InfoItemFigure)
            .where(InfoItemFigure.item_id.in_(item_ids))
            .order_by(InfoItemFigure.item_id, InfoItemFigure.figure_index)
        ).all()
        for f in figs:
            figs_by_item.setdefault(f.item_id, []).append(f)

    return [_result_out(db, r, items_map, figs_by_item) for r in results]


def _result_out(
    db: Session,
    r: AnalysisResult,
    items_map: dict[int, InfoItem],
    figs_by_item: dict[int, list[InfoItemFigure]],
) -> AnalysisResultOut:
    src = db.get(InfoSource, r.source_id) if r.source_id else None
    source_file: SourceFileOut | None = None
    if r.info_item_id and r.source_id:
        item = items_map.get(r.info_item_id)
        if item is not None:
            figs = figs_by_item.get(item.id, [])
            source_file = SourceFileOut(
                filename=item.title,
                file_path=item.external_id,
                title=item.title,
                author=item.author,
                author_affiliation=item.author_affiliation,
                published_at=item.article_published_at,
                page_count=item.page_count,
                extraction_method=item.extraction_method,
                file_url=f"/api/info-sources/{r.source_id}/items/{item.id}/file",
                figures=[
                    InfoItemFigureOut(
                        index=f.figure_index,
                        url=f"/api/info-sources/{r.source_id}/items/{item.id}/figures/{f.figure_index}",
                        mime=f.mime,
                        width=f.width,
                        height=f.height,
                    )
                    for f in figs
                ],
            )
    return AnalysisResultOut(
        id=r.id,
        task_run_id=r.task_run_id,
        task_id=r.task_id,
        source_id=r.source_id,
        source_name=src.name if src else None,
        info_item_id=r.info_item_id,
        result_type=r.result_type,
        content=r.content,
        created_at=r.created_at,
        source_file=source_file,
    )
