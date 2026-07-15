"""任务中心 endpoints: list task runs, view logs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..models.task import TaskLog, TaskRun
from ..models.user import User
from ..schemas.task import TaskLogOut, TaskRunDetailOut, TaskRunOut

router = APIRouter(prefix="/api/task-center", tags=["任务中心"])


@router.get("/runs", response_model=list[TaskRunOut])
def list_runs(
    kind: str | None = Query(None, description="analysis | sync"),
    status_: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_page("task_center")),
    db: Session = Depends(get_db),
):
    q = select(TaskRun).order_by(TaskRun.created_at.desc()).limit(limit)
    if kind:
        q = q.where(TaskRun.kind == kind)
    if status_:
        q = q.where(TaskRun.status == status_)
    return db.scalars(q).all()


@router.get("/runs/{run_id}", response_model=TaskRunDetailOut)
def get_run(
    run_id: int,
    _: User = Depends(require_page("task_center")),
    db: Session = Depends(get_db),
):
    run = db.get(TaskRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务运行不存在")
    return run


@router.get("/runs/{run_id}/logs", response_model=list[TaskLogOut])
def list_logs(
    run_id: int,
    _: User = Depends(require_page("task_center")),
    db: Session = Depends(get_db),
):
    run = db.get(TaskRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务运行不存在")
    return run.logs


@router.delete("/runs/{run_id}")
def delete_run(
    run_id: int,
    _: User = Depends(require_page("task_center")),
    db: Session = Depends(get_db),
):
    run = db.get(TaskRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务运行不存在")
    db.delete(run)
    db.commit()
    return {"detail": "已删除"}
