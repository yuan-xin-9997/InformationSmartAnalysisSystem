"""Info-source sync job (runs in the background worker).

Fetches items from an adapter, persists them as ``InfoItem`` rows (including
article metadata and embedded figures), backfills legacy items that lack
metadata/figures, and exposes ``reextract_item`` for manual re-extraction.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import or_, select

from ...core.config import settings
from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...core.timeutil import utcnow
from ...models.info_source import InfoItem, InfoItemFigure, InfoSource
from ...models.task import TaskLog, TaskRun
from .base import FigureData
from .factory import get_adapter

_logger = get_logger("sync")

# Cap on legacy items backfilled per sync run (avoids long-running syncs).
_BACKFILL_LIMIT = 200


def _content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _log(db, run_id: int, level: str, message: str) -> None:
    db.add(TaskLog(run_id=run_id, level=level, message=message))
    db.commit()


def _save_figures(
    db,
    item_id: int,
    figures: list[FigureData],
    figures_dir: Path,
) -> None:
    """Delete old figure rows + files for ``item_id``, then persist new ones.

    Files are written under ``figures_dir/YYYY/MM/DD/{item_id}_{index}.{ext}``.
    Old-file deletion is best-effort (missing files are silently skipped).
    """
    # --- clean old records + files ---
    old_figs = db.scalars(
        select(InfoItemFigure).where(InfoItemFigure.item_id == item_id)
    ).all()
    for old in old_figs:
        try:
            Path(old.storage_path).unlink(missing_ok=True)
        except Exception:
            pass
        db.delete(old)
    db.flush()

    # --- write new figures ---
    if not figures:
        return
    now = utcnow()
    sub = figures_dir / now.strftime("%Y/%m/%d")
    sub.mkdir(parents=True, exist_ok=True)
    for index, fig in enumerate(figures):
        fname = f"{item_id}_{index}.{fig.ext}"
        fpath = sub / fname
        fpath.write_bytes(fig.bytes_data)
        db.add(
            InfoItemFigure(
                item_id=item_id,
                figure_index=index,
                storage_path=str(fpath),
                mime=fig.mime,
                width=fig.width,
                height=fig.height,
                caption=None,
            )
        )


def _apply_metadata(item: InfoItem, extra: dict) -> None:
    """Copy the metadata fields from an adapter ``extra`` dict onto an item."""
    item.author = extra.get("author")
    item.author_affiliation = extra.get("author_affiliation")
    item.article_published_at = extra.get("article_published_at")
    item.page_count = extra.get("page_count")
    item.extraction_method = extra.get("extraction_method")


def run_sync(run_id: int, source_id: int) -> None:
    """Fetch new items for a source and upsert them. Updates the TaskRun."""
    with SessionLocal() as db:
        run = db.get(TaskRun, run_id)
        if run is None:
            return
        source = db.get(InfoSource, source_id)
        if source is None:
            run.status = "failed"
            run.error = "信息源不存在"
            run.finished_at = utcnow()
            db.commit()
            return

        run.status = "running"
        run.started_at = utcnow()
        db.commit()
        _log(db, run_id, "INFO", f"开始同步信息源: {source.name} ({source.type})")

        try:
            adapter = get_adapter(source.type, source.config or {})
            # 批量加载已存在条目 (external_id -> content_hash)，供增量回补与去重，
            # 避免逐条 N+1 查询（6000 文件时性能差距显著）。
            existing: dict[str, str] = {
                eid: ch
                for eid, ch in db.query(InfoItem.external_id, InfoItem.content_hash)
                .filter(InfoItem.source_id == source_id)
                .all()
            }
            items = adapter.fetch_new_items(
                since=source.last_sync_at,
                known_ids=set(existing.keys()),
            )
            new_count = 0
            updated_count = 0
            now = utcnow()
            for it in items:
                ch = _content_hash(it.content or it.external_id)
                if it.external_id not in existing:
                    item = InfoItem(
                        source_id=source_id,
                        external_id=it.external_id,
                        title=it.title,
                        url=it.url,
                        content=it.content,
                        content_hash=ch,
                        published_at=it.published_at,
                        fetched_at=now,
                    )
                    _apply_metadata(item, it.extra)
                    db.add(item)
                    db.flush()  # get item.id for figure FK
                    figures = it.extra.get("figures") or []
                    if figures:
                        _save_figures(db, item.id, figures, settings.figures_dir)
                    new_count += 1
                elif existing[it.external_id] != ch:
                    existing_item = db.scalars(
                        select(InfoItem).where(
                            InfoItem.source_id == source_id,
                            InfoItem.external_id == it.external_id,
                        )
                    ).first()
                    if existing_item is None:
                        continue
                    existing_item.title = it.title
                    existing_item.content = it.content
                    existing_item.content_hash = ch
                    existing_item.published_at = it.published_at
                    existing_item.fetched_at = now
                    existing_item.analyzed = False
                    _apply_metadata(existing_item, it.extra)
                    figures = it.extra.get("figures") or []
                    _save_figures(
                        db, existing_item.id, figures, settings.figures_dir
                    )
                    updated_count += 1

            # --- backfill: legacy items that lack metadata/figures, plus items
            # whose body text never extracted cleanly (extraction_method='none'
            # or empty content) so the vision fallback can retry them. ---
            backfill_count = 0
            if hasattr(adapter, "reextract") and source.type == "local_folder":
                # Only target items that existed BEFORE this run
                # (fetched_at < now). Newly created/updated items in this run
                # already carry fresh extraction_method/figures; re-processing
                # them here would double-save figures (their new-branch figure
                # rows are still pending, autoflush=False) and add noise.
                backfill_items = db.scalars(
                    select(InfoItem)
                    .where(
                        InfoItem.source_id == source_id,
                        InfoItem.fetched_at < now,
                        or_(
                            InfoItem.author.is_(None)
                            & InfoItem.page_count.is_(None),
                            InfoItem.extraction_method == "none",
                            InfoItem.content == "",
                        ),
                    )
                    .limit(_BACKFILL_LIMIT)
                ).all()
                for bf_item in backfill_items:
                    data = adapter.reextract(bf_item.external_id)
                    if data is None:
                        continue
                    ch = _content_hash(data.content or data.external_id)
                    new_figs = data.extra.get("figures") or []
                    # True only when the existing item still lacks a metadata
                    # field that re-extraction can provide -- i.e. backfill would
                    # actually fill something. Without this, items whose metadata
                    # is already complete (e.g. extraction_method='none' items
                    # retried each sync) would be re-written and re-analyzed
                    # every run.
                    has_new_metadata = any(
                        getattr(bf_item, k) is None and data.extra.get(k) is not None
                        for k in (
                            "author",
                            "author_affiliation",
                            "article_published_at",
                            "page_count",
                        )
                    )
                    # Skip if nothing actually changed (e.g. txt/md with no
                    # metadata and unchanged content) to avoid noisy re-writes.
                    if (
                        ch == bf_item.content_hash
                        and not has_new_metadata
                        and not new_figs
                        and data.title == bf_item.title
                    ):
                        continue
                    bf_item.title = data.title
                    bf_item.content = data.content
                    bf_item.url = data.url
                    bf_item.published_at = data.published_at
                    bf_item.content_hash = ch
                    bf_item.fetched_at = now
                    bf_item.analyzed = False
                    _apply_metadata(bf_item, data.extra)
                    _save_figures(db, bf_item.id, new_figs, settings.figures_dir)
                    backfill_count += 1
                if backfill_count:
                    _logger.info(
                        "回填元数据/图表: %d 条 (source=%s)", backfill_count, source.name
                    )
                    updated_count += backfill_count

            source.last_sync_at = now
            source.last_error = None
            source.status = "ok"
            db.flush()  # flush pending items so the count below sees them (autoflush=False)
            source.item_count = (
                db.query(InfoItem).filter(InfoItem.source_id == source_id).count()
            )
            run.status = "succeeded"
            run.finished_at = now
            run.summary = f"同步完成: 新增 {new_count} 条, 更新 {updated_count} 条"
            _log(db, run_id, "INFO", run.summary)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("信息源同步失败: %s", source.name)
            source.last_error = str(exc)
            source.status = "error"
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            _log(db, run_id, "ERROR", f"同步失败: {exc}")
            db.commit()


def reextract_item(source_id: int, item_id: int) -> dict:
    """Re-extract metadata + figures for a single item (group 5.2).

    Called by the API (task 4). Cleans old figure files/rows, re-extracts from
    the source file, updates the item, and returns ``{"item_id", "updated"}``.
    Raises ``ValueError`` if the item/source is invalid or re-extraction fails.
    """
    with SessionLocal() as db:
        item = db.get(InfoItem, item_id)
        if item is None or item.source_id != source_id:
            raise ValueError("信息项不存在或不属于该信息源")
        source = db.get(InfoSource, source_id)
        if source is None:
            raise ValueError("信息源不存在")
        adapter = get_adapter(source.type, source.config or {})
        data = adapter.reextract(item.external_id)
        if data is None:
            raise ValueError("文件不存在或源不支持重新抽取")

        ch = _content_hash(data.content or data.external_id)
        item.title = data.title
        item.content = data.content
        item.url = data.url
        item.published_at = data.published_at
        item.content_hash = ch
        item.fetched_at = utcnow()
        item.analyzed = False
        _apply_metadata(item, data.extra)
        new_figs = data.extra.get("figures") or []
        _save_figures(db, item.id, new_figs, settings.figures_dir)
        db.commit()
        return {"item_id": item_id, "updated": True}
