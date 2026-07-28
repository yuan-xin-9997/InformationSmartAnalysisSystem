"""InfoItem metadata columns and InfoItemFigure model tests."""
from __future__ import annotations

import pytest


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


def _make_source(db_session) -> int:
    from app.backend.models.info_source import InfoSource

    src = InfoSource(name="fig-test", type="local_folder", config={})
    db_session.add(src)
    db_session.commit()
    return src.id


def test_info_item_new_columns_nullable_by_default(db_session):
    """New metadata columns must be nullable and default to None."""
    from app.backend.models.info_source import InfoItem

    src_id = _make_source(db_session)
    item = InfoItem(source_id=src_id, external_id="ext-1", title="t")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    assert item.author is None
    assert item.author_affiliation is None
    assert item.article_published_at is None
    assert item.page_count is None


def test_info_item_new_columns_settable(db_session):
    """New metadata columns accept values."""
    from datetime import datetime

    from app.backend.models.info_source import InfoItem

    src_id = _make_source(db_session)
    item = InfoItem(
        source_id=src_id,
        external_id="ext-2",
        title="t",
        author="张三",
        author_affiliation="某机构",
        article_published_at=datetime(2026, 1, 15, 10, 30),
        page_count=5,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    assert item.author == "张三"
    assert item.author_affiliation == "某机构"
    assert item.article_published_at == datetime(2026, 1, 15, 10, 30)
    assert item.page_count == 5


def test_info_item_figure_created(db_session):
    """InfoItemFigure can be created and linked to an InfoItem."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure

    src_id = _make_source(db_session)
    item = InfoItem(source_id=src_id, external_id="ext-3", title="t")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    fig = InfoItemFigure(
        item_id=item.id,
        figure_index=0,
        storage_path="data/figures/item-3/fig-0.png",
        mime="image/png",
        width=800,
        height=600,
        caption="示例图",
    )
    db_session.add(fig)
    db_session.commit()
    db_session.refresh(fig)

    assert fig.id is not None
    assert fig.item_id == item.id
    assert fig.figure_index == 0
    assert fig.storage_path == "data/figures/item-3/fig-0.png"
    assert fig.mime == "image/png"
    assert fig.width == 800
    assert fig.height == 600
    assert fig.caption == "示例图"
    assert fig.created_at is not None


def test_info_item_figure_nullable_fields(db_session):
    """width, height, caption are nullable."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure

    src_id = _make_source(db_session)
    item = InfoItem(source_id=src_id, external_id="ext-4", title="t")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    fig = InfoItemFigure(
        item_id=item.id,
        figure_index=0,
        storage_path="data/figures/fig.svg",
        mime="image/svg+xml",
    )
    db_session.add(fig)
    db_session.commit()
    db_session.refresh(fig)

    assert fig.width is None
    assert fig.height is None
    assert fig.caption is None


def test_figures_relationship(db_session):
    """InfoItem.figures relationship works bidirectionally."""
    from app.backend.models.info_source import InfoItem, InfoItemFigure

    src_id = _make_source(db_session)
    item = InfoItem(source_id=src_id, external_id="ext-5", title="t")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    fig1 = InfoItemFigure(
        item_id=item.id, figure_index=0, storage_path="p0.png", mime="image/png"
    )
    fig2 = InfoItemFigure(
        item_id=item.id, figure_index=1, storage_path="p1.png", mime="image/png"
    )
    db_session.add_all([fig1, fig2])
    db_session.commit()
    db_session.refresh(item)

    assert len(item.figures) == 2
    # back_populates: figure.item refers back to the InfoItem
    assert fig1.item.id == item.id
    assert fig2.item.id == item.id
    # ordered by figure_index for determinism
    indices = sorted(f.figure_index for f in item.figures)
    assert indices == [0, 1]


def test_cascade_delete_item_deletes_figures(db_session):
    """Deleting an InfoItem must cascade-delete its InfoItemFigure rows."""
    from sqlalchemy import select

    from app.backend.models.info_source import InfoItem, InfoItemFigure

    src_id = _make_source(db_session)
    item = InfoItem(source_id=src_id, external_id="ext-6", title="t")
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    fig1 = InfoItemFigure(
        item_id=item.id, figure_index=0, storage_path="p0.png", mime="image/png"
    )
    fig2 = InfoItemFigure(
        item_id=item.id, figure_index=1, storage_path="p1.png", mime="image/png"
    )
    db_session.add_all([fig1, fig2])
    db_session.commit()

    # Confirm figures exist
    assert db_session.scalar(
        select(InfoItemFigure).where(InfoItemFigure.item_id == item.id)
    ) is not None

    # Delete the item
    db_session.delete(item)
    db_session.commit()

    # Figures must be cascade-deleted
    remaining = db_session.scalars(
        select(InfoItemFigure).where(InfoItemFigure.item_id == item.id)
    ).all()
    assert remaining == []


def test_cascade_delete_source_deletes_item_and_figures(db_session):
    """Deleting an InfoSource cascades through InfoItem to InfoItemFigure."""
    from sqlalchemy import select

    from app.backend.models.info_source import InfoItem, InfoItemFigure, InfoSource

    src = InfoSource(name="cascade-src", type="local_folder", config={})
    item = InfoItem(source_id=None, external_id="ext-7", title="t")
    db_session.add(src)
    db_session.commit()
    item.source_id = src.id
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)

    fig = InfoItemFigure(
        item_id=item.id, figure_index=0, storage_path="p.png", mime="image/png"
    )
    db_session.add(fig)
    db_session.commit()

    # Delete the source -> item -> figure all cascade
    db_session.delete(src)
    db_session.commit()

    assert db_session.get(InfoItem, item.id) is None
    assert db_session.scalars(select(InfoItemFigure)).all() == []


def test_info_item_figures_table_created_by_init_db():
    """init_db() / create_all produces the info_item_figures table."""
    from sqlalchemy import inspect

    from app.backend.core.database import engine

    insp = inspect(engine)
    assert insp.has_table("info_item_figures")
    cols = {c["name"] for c in insp.get_columns("info_item_figures")}
    expected = {
        "id",
        "item_id",
        "figure_index",
        "storage_path",
        "mime",
        "width",
        "height",
        "caption",
        "created_at",
    }
    assert expected <= cols, f"missing cols: {expected - cols}"


def test_info_items_table_has_new_columns():
    """info_items table has the new metadata columns after create_all."""
    from sqlalchemy import inspect

    from app.backend.core.database import engine

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("info_items")}
    for col in ("author", "author_affiliation", "article_published_at", "page_count"):
        assert col in cols, f"missing column: {col}"
