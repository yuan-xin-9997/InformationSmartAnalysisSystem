"""TDD tests for sync figures backfill + reextract_item (task 2).

Covers spec scenarios:
- Backfill: legacy InfoItem (author=NULL, page_count=NULL) gets metadata + figures
  on re-sync.
- reextract_item: re-extracts metadata + figures, updates item, returns dict.
- Idempotency: calling reextract_item twice yields consistent results.
- Old figure file cleanup: reextract deletes old figure files before writing new ones.
"""
from __future__ import annotations

import struct
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# ---------- fixtures ----------


@pytest.fixture
def db_session():
    """A clean SQLite session with all tables created fresh."""
    from app.backend import models  # noqa: F401  (register ORM models)
    from app.backend.core.database import Base, SessionLocal, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------- helpers ----------


def _make_png(width: int = 2, height: int = 3, color: tuple = (255, 0, 0)) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = b"IHDR" + ihdr_data
    ihdr_chunk = (
        struct.pack(">I", len(ihdr_data))
        + ihdr
        + struct.pack(">I", zlib.crc32(ihdr) & 0xFFFFFFFF)
    )
    raw = b""
    px = bytes(color)
    for _ in range(height):
        raw += b"\x00" + px * width
    compressed = zlib.compress(raw)
    idat = b"IDAT" + compressed
    idat_chunk = (
        struct.pack(">I", len(compressed))
        + idat
        + struct.pack(">I", zlib.crc32(idat) & 0xFFFFFFFF)
    )
    iend = b"IEND"
    iend_chunk = (
        struct.pack(">I", 0)
        + iend
        + struct.pack(">I", zlib.crc32(iend) & 0xFFFFFFFF)
    )
    return sig + ihdr_chunk + idat_chunk + iend_chunk


def _make_pdf(
    path: Path,
    title: str | None = "T",
    author: str | None = "A",
    text_lines: list[str] | None = None,
    image_paths: list[Path] | None = None,
) -> None:
    import fitz

    doc = fitz.open()
    md: dict[str, str] = {}
    if title is not None:
        md["title"] = title
    if author is not None:
        md["author"] = author
    if md:
        doc.set_metadata(md)
    page = doc.new_page()
    if text_lines:
        page.insert_text((50, 50), "\n".join(text_lines), fontname="china-s")
    if image_paths:
        for img in image_paths:
            rect = fitz.Rect(0, 0, 100, 100)
            page.insert_image(rect, filename=str(img))
    doc.save(str(path))
    doc.close()


def _make_source(db_session, folder: Path, name: str = "s") -> int:
    from app.backend.models.info_source import InfoSource

    src = InfoSource(
        name=name,
        type="local_folder",
        config={"folder_path": str(folder), "patterns": ["*.pdf"]},
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)
    return src.id


def _make_task_run(db_session, source_id: int, name: str = "s") -> int:
    from app.backend.models.task import TaskRun

    run = TaskRun(kind="sync", ref_id=source_id, ref_name=name, status="pending")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run.id


def _new_session():
    from app.backend.core.database import SessionLocal

    return SessionLocal()


# ---------- backfill ----------


def test_backfill_fills_metadata_and_figures(db_session, tmp_path):
    """Legacy item (no metadata, no figures) is backfilled on re-sync."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure
    from app.backend.services.info_source.sync import run_sync

    img = tmp_path / "img.png"
    img.write_bytes(_make_png(2, 3))
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, title="T", author="A", text_lines=["北京大学"], image_paths=[img])

    source_id = _make_source(db_session, tmp_path)
    # Legacy item: exists but lacks metadata + figures.
    item = InfoItem(
        source_id=source_id,
        external_id=str(pdf.resolve()),
        title="doc.pdf",
        content="old content",
        content_hash="legacy-hash",
        author=None,
        page_count=None,
    )
    db_session.add(item)
    db_session.commit()
    item_id = item.id

    # Set last_sync_at to future so fetch_new_items skips this file (simulating
    # "already synced, unchanged") and backfill picks it up.
    from app.backend.models.info_source import InfoSource

    src = db_session.get(InfoSource, source_id)
    src.last_sync_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()

    run_id = _make_task_run(db_session, source_id)
    db_session.close()

    run_sync(run_id, source_id)

    with _new_session() as db:
        refreshed = db.get(InfoItem, item_id)
        assert refreshed is not None
        assert refreshed.author == "A"
        assert refreshed.page_count == 1
        assert refreshed.author_affiliation is not None
        assert "北京大学" in refreshed.author_affiliation
        assert refreshed.title == "T"
        figs = (
            db.query(InfoItemFigure)
            .filter(InfoItemFigure.item_id == item_id)
            .order_by(InfoItemFigure.figure_index)
            .all()
        )
        assert len(figs) == 1
        assert figs[0].width == 2
        assert figs[0].height == 3
        assert figs[0].mime == "image/png"
        # File exists on disk
        assert Path(figs[0].storage_path).exists()


def test_backfill_skips_txt_with_nothing_to_fill(db_session, tmp_path):
    """txt items that have no metadata/figures and unchanged content are not
    counted as updated (avoid noise on every re-sync)."""
    from app.backend.models.info_source import InfoItem, InfoSource
    from app.backend.services.info_source.sync import run_sync

    txt = tmp_path / "a.txt"
    txt.write_text("hello", encoding="utf-8")

    # Create a txt-type source
    src = InfoSource(
        name="txt-src",
        type="local_folder",
        config={"folder_path": str(tmp_path), "patterns": ["*.txt"]},
    )
    db_session.add(src)
    db_session.commit()
    db_session.refresh(src)
    source_id = src.id

    # Legacy txt item
    import hashlib

    real_hash = hashlib.sha256(b"hello").hexdigest()
    item = InfoItem(
        source_id=source_id,
        external_id=str(txt.resolve()),
        title="a.txt",
        content="hello",
        content_hash=real_hash,
        author=None,
        page_count=None,
    )
    db_session.add(item)
    db_session.commit()
    item_id = item.id

    src.last_sync_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()

    run_id = _make_task_run(db_session, source_id, name="txt-src")
    db_session.close()

    run_sync(run_id, source_id)

    with _new_session() as db:
        from app.backend.models.task import TaskRun

        run = db.get(TaskRun, run_id)
        # No new items, no updates (txt has nothing to backfill)
        assert "更新 0 条" in run.summary
        refreshed = db.get(InfoItem, item_id)
        assert refreshed.author is None
        assert refreshed.page_count is None


# ---------- reextract_item ----------


def test_reextract_item_updates_metadata_and_figures(db_session, tmp_path):
    from app.backend.models.info_source import InfoItem, InfoItemFigure
    from app.backend.services.info_source.sync import reextract_item

    img = tmp_path / "img.png"
    img.write_bytes(_make_png(2, 3))
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, title="T", author="A", text_lines=["清华大学"], image_paths=[img])

    source_id = _make_source(db_session, tmp_path)
    item = InfoItem(
        source_id=source_id,
        external_id=str(pdf.resolve()),
        title="old-title",
        content="old",
        content_hash="old",
    )
    db_session.add(item)
    db_session.commit()
    item_id = item.id
    db_session.close()

    result = reextract_item(source_id, item_id)
    assert result["item_id"] == item_id
    assert result["updated"] is True

    with _new_session() as db:
        refreshed = db.get(InfoItem, item_id)
        assert refreshed.title == "T"
        assert refreshed.author == "A"
        assert refreshed.author_affiliation is not None
        assert "清华大学" in refreshed.author_affiliation
        assert refreshed.page_count == 1
        figs = db.query(InfoItemFigure).filter(InfoItemFigure.item_id == item_id).all()
        assert len(figs) == 1


def test_reextract_item_idempotent(db_session, tmp_path):
    """Calling reextract_item twice produces the same result."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure
    from app.backend.services.info_source.sync import reextract_item

    img = tmp_path / "img.png"
    img.write_bytes(_make_png(2, 3))
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, title="T", author="A", image_paths=[img])

    source_id = _make_source(db_session, tmp_path)
    item = InfoItem(
        source_id=source_id,
        external_id=str(pdf.resolve()),
        title="old",
        content="old",
        content_hash="old",
    )
    db_session.add(item)
    db_session.commit()
    item_id = item.id
    db_session.close()

    reextract_item(source_id, item_id)
    reextract_item(source_id, item_id)  # second call

    with _new_session() as db:
        refreshed = db.get(InfoItem, item_id)
        assert refreshed.title == "T"
        assert refreshed.author == "A"
        figs = (
            db.query(InfoItemFigure)
            .filter(InfoItemFigure.item_id == item_id)
            .order_by(InfoItemFigure.figure_index)
            .all()
        )
        assert len(figs) == 1  # still 1, not 2 (old deleted before new saved)


def test_reextract_item_cleans_old_figure_files(db_session, tmp_path):
    """reextract deletes old figure files before writing new ones."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure
    from app.backend.services.info_source.sync import _save_figures, reextract_item
    from app.backend.services.info_source.base import FigureData
    from app.backend.core.config import settings

    img = tmp_path / "img.png"
    img.write_bytes(_make_png(2, 3))
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, title="T", author="A", image_paths=[img])

    source_id = _make_source(db_session, tmp_path)
    item = InfoItem(
        source_id=source_id,
        external_id=str(pdf.resolve()),
        title="old",
        content="old",
        content_hash="old",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    item_id = item.id

    # Save a "stale" figure so there's an old file to clean.
    stale_fig = FigureData(
        bytes_data=_make_png(9, 9, color=(0, 255, 0)),
        ext="png",
        mime="image/png",
        width=9,
        height=9,
    )
    _save_figures(db_session, item_id, [stale_fig], settings.figures_dir)
    db_session.commit()

    # Confirm stale file exists
    with _new_session() as db:
        old_figs = db.query(InfoItemFigure).filter(InfoItemFigure.item_id == item_id).all()
        assert len(old_figs) == 1
        old_path = Path(old_figs[0].storage_path)
        assert old_path.exists()

    db_session.close()
    reextract_item(source_id, item_id)

    with _new_session() as db:
        figs = db.query(InfoItemFigure).filter(InfoItemFigure.item_id == item_id).all()
        assert len(figs) == 1
        new_path = Path(figs[0].storage_path)
        assert new_path.exists()
        # Old file should be gone (different content -> different path unlikely,
        # but the old file path must no longer exist if different).
        if old_path != new_path:
            assert not old_path.exists()
        # New figure dimensions match the reextracted image
        assert figs[0].width == 2
        assert figs[0].height == 3


def test_reextract_item_missing_file_raises(db_session, tmp_path):
    """reextract_item raises ValueError when the source file is gone."""
    import pytest as _pytest

    from app.backend.models.info_source import InfoItem
    from app.backend.services.info_source.sync import reextract_item

    source_id = _make_source(db_session, tmp_path)
    item = InfoItem(
        source_id=source_id,
        external_id=str(tmp_path / "gone.pdf"),
        title="gone",
        content="x",
        content_hash="x",
    )
    db_session.add(item)
    db_session.commit()
    item_id = item.id
    db_session.close()

    with _pytest.raises(ValueError, match="文件不存在或源不支持重新抽取"):
        reextract_item(source_id, item_id)


def test_reextract_item_wrong_source_raises(db_session, tmp_path):
    """reextract_item raises when item doesn't belong to the given source."""
    import pytest as _pytest

    from app.backend.models.info_source import InfoItem

    source_id = _make_source(db_session, tmp_path, name="s1")
    other_source_id = _make_source(db_session, tmp_path, name="s2")
    item = InfoItem(
        source_id=source_id,
        external_id=str(tmp_path / "x.pdf"),
        title="x",
        content="x",
        content_hash="x",
    )
    db_session.add(item)
    db_session.commit()
    item_id = item.id
    db_session.close()

    from app.backend.services.info_source.sync import reextract_item

    with _pytest.raises(ValueError):
        reextract_item(other_source_id, item_id)


# ---------- new-branch carries metadata + figures ----------


def test_sync_new_item_persists_metadata_and_figures(db_session, tmp_path):
    """First sync of a PDF persists metadata + figures (new branch)."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure
    from app.backend.services.info_source.sync import run_sync

    img = tmp_path / "img.png"
    img.write_bytes(_make_png(2, 3))
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, title="T", author="A", text_lines=["中国科学院"], image_paths=[img])

    source_id = _make_source(db_session, tmp_path)
    run_id = _make_task_run(db_session, source_id)
    db_session.close()

    run_sync(run_id, source_id)

    with _new_session() as db:
        item = db.query(InfoItem).filter(InfoItem.source_id == source_id).one()
        assert item.title == "T"
        assert item.author == "A"
        assert item.author_affiliation is not None
        assert "中国科学院" in item.author_affiliation
        assert item.page_count == 1
        figs = db.query(InfoItemFigure).filter(InfoItemFigure.item_id == item.id).all()
        assert len(figs) == 1
        assert figs[0].width == 2
        assert figs[0].height == 3
        assert Path(figs[0].storage_path).exists()


def test_sync_update_branch_updates_metadata(db_session, tmp_path):
    """When content changes (hash differs), metadata is re-extracted and updated."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure
    from app.backend.services.info_source.sync import run_sync

    img = tmp_path / "img.png"
    img.write_bytes(_make_png(2, 3))
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, title="NewTitle", author="NewAuthor", text_lines=["复旦大学"], image_paths=[img])

    source_id = _make_source(db_session, tmp_path)
    # Pre-existing item with stale metadata + a stale figure
    item = InfoItem(
        source_id=source_id,
        external_id=str(pdf.resolve()),
        title="OldTitle",
        content="old content",
        content_hash="stale-hash",
        author="OldAuthor",
        author_affiliation="Old",
        page_count=99,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    item_id = item.id

    # Add a stale figure to verify it gets replaced
    from app.backend.services.info_source.base import FigureData
    from app.backend.services.info_source.sync import _save_figures
    from app.backend.core.config import settings

    stale = FigureData(
        bytes_data=_make_png(9, 9),
        ext="png",
        mime="image/png",
        width=9,
        height=9,
    )
    _save_figures(db_session, item_id, [stale], settings.figures_dir)
    db_session.commit()

    # Don't set last_sync_at (first sync, since=None) -> fetch_new_items returns
    # the file; hash differs -> update branch fires.
    run_id = _make_task_run(db_session, source_id)
    db_session.close()

    run_sync(run_id, source_id)

    with _new_session() as db:
        refreshed = db.get(InfoItem, item_id)
        assert refreshed.title == "NewTitle"
        assert refreshed.author == "NewAuthor"
        assert "复旦大学" in refreshed.author_affiliation
        assert refreshed.page_count == 1
        figs = db.query(InfoItemFigure).filter(InfoItemFigure.item_id == item_id).all()
        assert len(figs) == 1
        assert figs[0].width == 2  # new image, not 9
