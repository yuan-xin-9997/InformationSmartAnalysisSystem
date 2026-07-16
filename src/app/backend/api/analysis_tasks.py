"""Analysis-task endpoints: CRUD, bind sources, trigger analysis, view results."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..models.analysis import AnalysisResult, AnalysisTask, TaskSource
from ..models.info_source import InfoSource
from ..models.task import TaskRun
from ..models.user import User
from ..schemas.analysis import (
    AnalysisResultOut,
    AnalysisTaskCreate,
    AnalysisTaskDetailOut,
    AnalysisTaskOut,
    AnalysisTaskUpdate,
    RunAnalysisRequest,
    TaskSourceOut,
)
from ..services import worker
from ..services.analysis import run_analysis

router = APIRouter(prefix="/api/analysis-tasks", tags=["分析任务"])
results_router = APIRouter(prefix="/api/analysis-results", tags=["分析结果"])


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
    db.commit()
    db.refresh(task)
    detail = AnalysisTaskDetailOut.model_validate(task)
    detail.sources = _build_sources(task)
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
    db.commit()
    db.refresh(task)
    detail = AnalysisTaskDetailOut.model_validate(task)
    detail.sources = _build_sources(task)
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
    # 自定义模式（任务 config.mode=custom 或运行 mode=custom）：运行记录标记为 custom。
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
    return [_result_out(db, r) for r in results]


@results_router.get("", response_model=list[AnalysisResultOut])
def list_results(
    run_id: int | None = Query(None),
    task_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_page("analysis_result")),
    db: Session = Depends(get_db),
):
    q = select(AnalysisResult).order_by(AnalysisResult.id.desc()).limit(limit)
    if run_id:
        q = q.where(AnalysisResult.task_run_id == run_id)
    if task_id:
        q = q.where(AnalysisResult.task_id == task_id)
    results = db.scalars(q).all()
    return [_result_out(db, r) for r in results]


def _result_out(db: Session, r: AnalysisResult) -> AnalysisResultOut:
    src = db.get(InfoSource, r.source_id) if r.source_id else None
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
    )
