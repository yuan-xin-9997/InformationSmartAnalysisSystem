"""Information-source management endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.deps import require_page
from ..models.info_source import InfoItem, InfoItemFigure, InfoSource
from ..models.task import TaskRun
from ..models.user import User
from ..schemas.info_source import (
    InfoItemBrief,
    InfoItemOut,
    InfoSourceCreate,
    InfoSourceOut,
    InfoSourceUpdate,
    ItemsQueryRequest,
    ItemsQueryResponse,
    SourceStatusOut,
)
from ..services import worker
from ..services.info_source import get_adapter, validate_config
from ..services.info_source.factory import type_specs
from ..services.info_source.sync import reextract_item, run_sync

router = APIRouter(prefix="/api/info-sources", tags=["信息源管理"])


@router.get("/types")
def get_types(_: User = Depends(require_page("info_sources"))):
    """Supported source types + their required config keys (for the form)."""
    return type_specs()


# 选择条目弹窗列排序的白名单：sort_by 值 -> ORM 列。未知值回退 id 倒序，防注入。
_SORT_COLUMNS = {
    "title": InfoItem.title,
    "published_at": InfoItem.published_at,
    "analyzed": InfoItem.analyzed,
    "created_at": InfoItem.created_at,
}


@router.post("/items/query", response_model=ItemsQueryResponse)
def query_items(
    req: ItemsQueryRequest,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    """跨多个信息源分页查询条目（供自定义分析模式的条目选择器）。

    支持已选取数(`ids`)、排除已选(`exclude_ids`)、按白名单列排序(`sort_by`/`order`)、
    标题模糊匹配(`keyword`)。所有过滤均在 SQL 层统一应用后再分页，保证每页满额。
    """
    if not req.source_ids:
        return ItemsQueryResponse(items=[], total=0)

    stmt = select(InfoItem).where(InfoItem.source_id.in_(req.source_ids))
    if req.analyzed is not None:
        stmt = stmt.where(InfoItem.analyzed == req.analyzed)
    if req.ids:
        stmt = stmt.where(InfoItem.id.in_(req.ids))
    if req.exclude_ids:
        stmt = stmt.where(InfoItem.id.not_in(req.exclude_ids))
    if req.keyword:
        stmt = stmt.where(InfoItem.title.ilike(f"%{req.keyword}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    col = _SORT_COLUMNS.get(req.sort_by) if req.sort_by else None
    if col is None:
        # 缺省或非白名单字段：回退默认 id 倒序（忽略 order），与现状一致且防注入
        stmt = stmt.order_by(InfoItem.id.desc())
    else:
        stmt = stmt.order_by(col.asc() if req.order == "asc" else col.desc())
    stmt = stmt.limit(req.limit).offset(req.offset)

    rows = db.scalars(stmt).all()
    return ItemsQueryResponse(items=rows, total=total)


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


# ---------- file preview / figure serving / reextract (task 4) ----------

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def _get_owned_item(
    db: Session, source_id: int, item_id: int
) -> InfoItem:
    """Return the InfoItem if it exists and belongs to ``source_id``, else 404."""
    item = db.get(InfoItem, item_id)
    if item is None or item.source_id != source_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="信息项不存在"
        )
    return item


@router.get("/{source_id}/items/{item_id}/file")
def get_item_file(
    source_id: int,
    item_id: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    """Preview/download the source file backing an InfoItem.

    - PDF: inline (browser-embedded preview)
    - docx: attachment (download)
    - html/txt/md: text/plain (never text/html, to avoid XSS)
    """
    item = _get_owned_item(db, source_id, item_id)
    src = db.get(InfoSource, source_id)
    if src is None or src.type != "local_folder":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该信息源类型不支持文件预览",
        )

    file_path = Path(item.external_id)
    folder_root_raw = src.config.get("folder_path")
    if not folder_root_raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该信息源未配置 folder_path",
        )
    folder_root = Path(folder_root_raw).resolve()
    resolved = file_path.resolve()
    # Path-traversal defense: the file must live under the source's folder_path.
    if not resolved.is_relative_to(folder_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="路径不在允许范围内"
        )
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
        )

    suffix = resolved.suffix.lower()
    if suffix == ".pdf":
        return FileResponse(
            str(resolved),
            media_type="application/pdf",
            filename=item.title or resolved.name,
            content_disposition_type="inline",
        )
    if suffix == ".docx":
        return FileResponse(
            str(resolved),
            media_type=_DOCX_MEDIA_TYPE,
            filename=item.title or resolved.name,
            content_disposition_type="attachment",
        )
    if suffix in (".html", ".htm", ".txt", ".md"):
        return PlainTextResponse(
            resolved.read_text(encoding="utf-8", errors="ignore"),
            media_type="text/plain; charset=utf-8",
        )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="不支持的文件类型"
    )


@router.get("/{source_id}/items/{item_id}/figures/{index}")
def get_item_figure(
    source_id: int,
    item_id: int,
    index: int,
    _: User = Depends(require_page("analysis_tasks")),
    db: Session = Depends(get_db),
):
    """Serve a single figure image (by index) belonging to an InfoItem."""
    _get_owned_item(db, source_id, item_id)

    fig = db.scalars(
        select(InfoItemFigure).where(
            InfoItemFigure.item_id == item_id,
            InfoItemFigure.figure_index == index,
        )
    ).first()
    if fig is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="图表不存在"
        )

    fig_path = Path(fig.storage_path).resolve()
    # Path-traversal defense: the figure must live under figures_dir.
    if not fig_path.is_relative_to(settings.figures_dir.resolve()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="路径不在允许范围内"
        )
    if not fig_path.exists() or not fig_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
        )
    return FileResponse(str(fig_path), media_type=fig.mime or "application/octet-stream")


@router.post("/{source_id}/items/{item_id}/reextract")
def reextract_item_api(
    source_id: int,
    item_id: int,
    _: User = Depends(require_page("info_sources")),
    db: Session = Depends(get_db),
):
    """Manually re-extract metadata + figures for a single item."""
    _get_owned_item(db, source_id, item_id)
    try:
        result = reextract_item(source_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return result
