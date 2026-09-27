"""Ensure bound inputs are current before an analysis run."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from ...core.database import SessionLocal
from ...core.timeutil import utcnow, iso_beijing
from ...models.info_source import InfoSource
from ...models.task import TaskRun
from .sync import run_sync, source_lock


@dataclass
class RefreshResult:
    source_id: int
    source_name: str
    status: str
    added_count: int
    updated_count: int
    error: str | None
    started_at: str
    finished_at: str
    reason: str | None = None


def refresh(source_id: int, max_age_seconds: int = 900) -> RefreshResult:
    """Wait for an in-flight update, then check freshness under the same lock."""
    with source_lock(source_id):
        started = utcnow()
        with SessionLocal() as db:
            source = db.get(InfoSource, source_id)
            if source is None:
                return RefreshResult(source_id, "(已删除)", "failed", 0, 0,
                                     "信息源不存在", started.isoformat(), utcnow().isoformat())
            name = source.name
            if source.type not in ("local_folder", "website", "freshrss"):
                return RefreshResult(source_id, name, "skipped", 0, 0, None,
                                     started.isoformat(), utcnow().isoformat(), "此来源不支持更新")
            previous = source.last_sync_at
            if previous and previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            if (source.type != "local_folder" and source.status == "ok" and previous
                    and (started - previous).total_seconds() < max_age_seconds):
                return RefreshResult(source_id, name, "skipped", 0, 0, None,
                                     started.isoformat(), utcnow().isoformat(), "仍在数据新鲜度有效期内")
            sync_run = TaskRun(kind="sync", ref_id=source_id, ref_name=name, status="pending")
            db.add(sync_run)
            db.commit()
            sync_id = sync_run.id
        run_sync(sync_id, source_id)
        with SessionLocal() as db:
            result = db.get(TaskRun, sync_id)
            source = db.get(InfoSource, source_id)
            counts = result.refresh_detail or {}
            return RefreshResult(source_id, name,
                                 "succeeded" if result.status == "succeeded" and source.status == "ok" else "failed",
                                 counts.get("added_count", 0), counts.get("updated_count", 0),
                                 result.error or (source.last_error if source.status != "ok" else None),
                                 started.isoformat(), utcnow().isoformat())


def as_dict(result: RefreshResult) -> dict:
    data = asdict(result)
    for key in ("started_at", "finished_at"):
        data[key] = iso_beijing(datetime.fromisoformat(data[key]))
    return data
