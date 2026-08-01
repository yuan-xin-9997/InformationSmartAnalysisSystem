"""Collect email attachments (source file + figures) for push events.

Reuses the file-serving path validation (``is_relative_to``) to prevent path
traversal. Files exceeding the size limit or missing/outsider are skipped with
a warning log; the push is never aborted because of an attachment.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...core.config import settings
from ...core.logging import get_logger
from ...models.analysis import AnalysisResult
from ...models.info_source import InfoItem, InfoItemFigure, InfoSource

_logger = get_logger("push.attachments")

_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_FILE_MIME = {
    ".pdf": "application/pdf",
    ".docx": _DOCX_MEDIA_TYPE,
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
}


@dataclass
class Attachment:
    """A single email attachment."""

    filename: str
    mime: str
    data: bytes


def _safe_filename(name: str, fallback: str) -> str:
    """Return a basename-only filename (defends against header injection)."""
    return Path(name or fallback).name or fallback


def _try_read(path: Path, filename: str, mime: str) -> Attachment | None:
    """Read a file as an attachment; skip (with log) if missing/oversized/error."""
    try:
        if not path.exists() or not path.is_file():
            _logger.warning("附件跳过(文件不存在): %s", path)
            return None
        size = path.stat().st_size
        if size > _MAX_ATTACHMENT_BYTES:
            _logger.warning(
                "附件跳过(超 %d 字节): %s (%d bytes)", _MAX_ATTACHMENT_BYTES, path, size
            )
            return None
        return Attachment(filename=filename, mime=mime, data=path.read_bytes())
    except Exception:  # noqa: BLE001
        _logger.exception("附件读取失败: %s", path)
        return None


def collect_attachments(db, results: list[AnalysisResult]) -> list[Attachment]:
    """Collect source-file + figure attachments for ``per_item`` results.

    ``aggregate`` results (``info_item_id`` is None) contribute no attachments.
    """
    atts: list[Attachment] = []
    item_ids = {
        r.info_item_id
        for r in results
        if r.info_item_id and r.result_type == "per_item"
    }
    if not item_ids:
        return atts

    items_map = {
        it.id: it
        for it in db.query(InfoItem).filter(InfoItem.id.in_(item_ids)).all()
    }
    src_ids = {it.source_id for it in items_map.values()}
    srcs_map = (
        {s.id: s for s in db.query(InfoSource).filter(InfoSource.id.in_(src_ids)).all()}
        if src_ids
        else {}
    )
    figs = (
        db.query(InfoItemFigure)
        .filter(InfoItemFigure.item_id.in_(item_ids))
        .order_by(InfoItemFigure.item_id, InfoItemFigure.figure_index)
        .all()
    )

    figures_dir = Path(settings.figures_dir).resolve()

    # 原文件（仅 local_folder）
    for r in results:
        if r.result_type != "per_item" or not r.info_item_id:
            continue
        item = items_map.get(r.info_item_id)
        if not item:
            continue
        src = srcs_map.get(item.source_id)
        if not src or src.type != "local_folder":
            continue
        folder_raw = (src.config or {}).get("folder_path")
        if not folder_raw:
            continue
        folder_root = Path(folder_raw).resolve()
        file_path = Path(item.external_id).resolve()
        if not file_path.is_relative_to(folder_root):
            _logger.warning("原文件附件跳过(路径越界): %s", item.external_id)
            continue
        mime = _FILE_MIME.get(file_path.suffix.lower())
        if mime is None:
            continue
        att = _try_read(file_path, _safe_filename(item.title, file_path.name), mime)
        if att:
            atts.append(att)

    # 图表
    for f in figs:
        item = items_map.get(f.item_id)
        if not item:
            continue
        fig_path = Path(f.storage_path).resolve()
        if not fig_path.is_relative_to(figures_dir):
            _logger.warning("图表附件跳过(路径越界): %s", f.storage_path)
            continue
        stem = Path(_safe_filename(item.title, "figure")).stem
        filename = f"{stem}_{f.figure_index}{fig_path.suffix.lower()}"
        att = _try_read(fig_path, filename, f.mime or "application/octet-stream")
        if att:
            atts.append(att)

    return atts
