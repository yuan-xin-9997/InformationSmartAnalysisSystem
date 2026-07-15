"""Info-source sync job (runs in the background worker)."""
from __future__ import annotations

import hashlib

from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...core.timeutil import utcnow
from ...models.info_source import InfoItem, InfoSource
from ...models.task import TaskLog, TaskRun
from .factory import get_adapter

_logger = get_logger("sync")


def _content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _log(db, run_id: int, level: str, message: str) -> None:
    db.add(TaskLog(run_id=run_id, level=level, message=message))
    db.commit()


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
            items = adapter.fetch_new_items()
            new_count = 0
            updated_count = 0
            now = utcnow()
            for it in items:
                ch = _content_hash(it.content or it.external_id)
                existing = (
                    db.query(InfoItem)
                    .filter(
                        InfoItem.source_id == source_id,
                        InfoItem.external_id == it.external_id,
                    )
                    .first()
                )
                if existing is None:
                    db.add(
                        InfoItem(
                            source_id=source_id,
                            external_id=it.external_id,
                            title=it.title,
                            url=it.url,
                            content=it.content,
                            content_hash=ch,
                            published_at=it.published_at,
                            fetched_at=now,
                        )
                    )
                    new_count += 1
                elif existing.content_hash != ch:
                    existing.title = it.title
                    existing.content = it.content
                    existing.content_hash = ch
                    existing.published_at = it.published_at
                    existing.fetched_at = now
                    existing.analyzed = False
                    updated_count += 1

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
