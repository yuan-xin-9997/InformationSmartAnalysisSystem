"""Information-source management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_page
from ..models.info_source import InfoItem, InfoSource
from ..models.task import TaskRun
from ..models.user import User
from ..schemas.info_source import (
    InfoItemBrief,
    InfoItemOut,
    InfoSourceCreate,
    InfoSourceOut,
    InfoSourceUpdate,
    SourceStatusOut,
)
from ..services import worker
from ..services.info_source import get_adapter, validate_config
from ..services.info_source.factory import type_specs
from ..services.info_source.sync import run_sync

router = APIRouter(prefix="/api/info-sources", tags=["信息源管理"])


@router.get("/types")
def get_types(_: User = Depends(require_page("info_sources"))):
    """Supported source types + their required config keys (for the form)."""
    return type_specs()


@router.get("", response_model=list[InfoSourceOut])
def list_sources(
    _: User = Depends(require_page("info_sources")), db: Session = Depends(get_db)
):
    return db.scalars(select(InfoSource).order_by(InfoSource.id)).all()


@router.post("", response_model=InfoSourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    req: InfoSourceCreate,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    try:
        validate_config(req.type, req.config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    src = InfoSource(name=req.name, type=req.type, config=req.config)
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


@router.get("/{source_id}", response_model=InfoSourceOut)
def get_source(
    source_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    src = db.get(InfoSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息源不存在")
    return src


@router.put("/{source_id}", response_model=InfoSourceOut)
def update_source(
    source_id: int,
    req: InfoSourceUpdate,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    src = db.get(InfoSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息源不存在")
    if req.name is not None:
        src.name = req.name
    if req.config is not None:
        try:
            validate_config(src.type, req.config)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        src.config = req.config
    db.commit()
    db.refresh(src)
    return src


@router.delete("/{source_id}")
def delete_source(
    source_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    src = db.get(InfoSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息源不存在")
    db.delete(src)
    db.commit()
    return {"detail": "已删除"}


@router.get("/{source_id}/status", response_model=SourceStatusOut)
def get_status(
    source_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    src = db.get(InfoSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息源不存在")
    return SourceStatusOut(
        status=src.status,
        message=src.last_error or "",
        item_count=src.item_count,
        last_sync_at=src.last_sync_at,
    )


@router.post("/{source_id}/check", response_model=SourceStatusOut)
def check_source(
    source_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    """Live health-check the source via its adapter (no item fetching)."""
    src = db.get(InfoSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息源不存在")
    try:
        adapter = get_adapter(src.type, src.config or {})
        result = adapter.check_status()
        src.status = "ok" if result.ok else "error"
        src.last_error = None if result.ok else result.message
        db.commit()
        return SourceStatusOut(
            status=src.status,
            message=result.message,
            item_count=src.item_count,
            last_sync_at=src.last_sync_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        return SourceStatusOut(
            status="error",
            message=str(exc),
            item_count=src.item_count,
            last_sync_at=src.last_sync_at,
        )


@router.post("/{source_id}/sync")
def sync_source(
    source_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    """Trigger a background sync; returns the TaskRun id immediately."""
    src = db.get(InfoSource, source_id)
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息源不存在")
    run = TaskRun(kind="sync", ref_id=source_id, ref_name=src.name, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    worker.submit(run_sync, run.id, source_id)
    return {"run_id": run.id, "status": "pending"}


@router.get("/{source_id}/items/count")
def count_items(
    source_id: int,
    analyzed: bool | None = Query(None, description="true=已分析,false=未分析,省略=全部"),
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    """返回条目计数（供分页）。total 为按 analyzed 过滤后的数；all/analyzed/unanalyzed 为整体统计。"""
    base = db.query(InfoItem).filter(InfoItem.source_id == source_id)
    all_count = base.count()
    analyzed_count = base.filter(InfoItem.analyzed.is_(True)).count()
    unanalyzed_count = base.filter(InfoItem.analyzed.is_(False)).count()
    if analyzed is True:
        shown = analyzed_count
    elif analyzed is False:
        shown = unanalyzed_count
    else:
        shown = all_count
    return {
        "total": shown,
        "all": all_count,
        "analyzed": analyzed_count,
        "unanalyzed": unanalyzed_count,
    }


@router.get("/{source_id}/items", response_model=list[InfoItemBrief])
def list_items(
    source_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    analyzed: bool | None = Query(None, description="true=已分析,false=未分析,省略=全部"),
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    q = select(InfoItem).where(InfoItem.source_id == source_id)
    if analyzed is not None:
        q = q.where(InfoItem.analyzed == analyzed)
    q = q.order_by(InfoItem.id.desc()).limit(limit).offset(offset)
    return db.scalars(q).all()


@router.get("/{source_id}/items/{item_id}", response_model=InfoItemOut)
def get_item(
    source_id: int,
    item_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    item = db.get(InfoItem, item_id)
    if item is None or item.source_id != source_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="信息项不存在")
    return item
