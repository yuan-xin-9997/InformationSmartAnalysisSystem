"""Tests for the ``extraction_method`` column migration (enhance-pdf-content-extraction).

Covers spec scenario: 均未产出有效文本时记录 none / 老行 NULL 语义。
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text


def test_ensure_column_adds_missing_column():
    """``_ensure_column`` adds the column when missing."""
    from app.backend.core.database import _ensure_column

    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE info_items (id INTEGER PRIMARY KEY, title TEXT)"))
    assert "extraction_method" not in {
        c["name"] for c in inspect(eng).get_columns("info_items")
    }

    _ensure_column(eng, "info_items", "extraction_method", "TEXT")

    cols = {c["name"] for c in inspect(eng).get_columns("info_items")}
    assert "extraction_method" in cols


def test_ensure_column_old_rows_stay_null():
    """Pre-existing rows keep NULL after the column is added (老行 NULL 语义)."""
    from app.backend.core.database import _ensure_column

    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE info_items (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO info_items (id, title) VALUES (1, 'old')"))

    _ensure_column(eng, "info_items", "extraction_method", "TEXT")

    with eng.begin() as conn:
        row = conn.execute(text("SELECT extraction_method FROM info_items WHERE id=1")).fetchone()
    assert row is not None
    assert row[0] is None  # old row untouched -> NULL


def test_ensure_column_idempotent():
    """``_ensure_column`` is a no-op when the column already exists (no error)."""
    from app.backend.core.database import _ensure_column

    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        conn.execute(
            text("CREATE TABLE info_items (id INTEGER PRIMARY KEY, extraction_method TEXT)")
        )
    _ensure_column(eng, "info_items", "extraction_method", "TEXT")  # must not raise
    assert "extraction_method" in {
        c["name"] for c in inspect(eng).get_columns("info_items")
    }


def test_ensure_column_noop_for_missing_table():
    """``_ensure_column`` is a no-op when the table doesn't exist yet."""
    from app.backend.core.database import _ensure_column

    eng = create_engine("sqlite:///:memory:")
    _ensure_column(eng, "info_items", "extraction_method", "TEXT")  # must not raise
    assert not inspect(eng).has_table("info_items")


def test_info_item_extraction_method_defaults_none():
    """A freshly created InfoItem has extraction_method=None."""
    from app.backend.core.database import Base, SessionLocal, engine, init_db
    from app.backend.models.info_source import InfoItem, InfoSource

    Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as db:
        src = InfoSource(name="s", type="local_folder", config={})
        db.add(src)
        db.flush()
        item = InfoItem(source_id=src.id, external_id="x", title="t", content="c")
        db.add(item)
        db.commit()
        db.refresh(item)
        assert item.extraction_method is None
