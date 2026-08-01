"""Push email attachment collection tests."""
from __future__ import annotations

import pathlib
import tempfile

from app.backend.core.config import settings
from app.backend.core.database import SessionLocal
from app.backend.models.analysis import AnalysisResult, AnalysisTask
from app.backend.models.info_source import InfoItem, InfoItemFigure, InfoSource
from app.backend.models.task import TaskRun
from app.backend.services.push.attachments import collect_attachments


def _figs_dir() -> pathlib.Path:
    d = pathlib.Path(settings.figures_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_result(db, src, item, result_type="per_item"):
    task = AnalysisTask(name="T", config={})
    db.add(task)
    db.flush()
    run = TaskRun(kind="analysis", ref_id=task.id, ref_name="T", status="succeeded")
    db.add(run)
    db.flush()
    r = AnalysisResult(
        task_run_id=run.id, task_id=task.id, source_id=src.id,
        info_item_id=item.id if item else None,
        result_type=result_type, content="c",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_collect_per_item_local_folder_file_and_figures(client):
    with SessionLocal() as db:
        folder = pathlib.Path(tempfile.mkdtemp())
        src = InfoSource(name="s", type="local_folder", config={"folder_path": str(folder)})
        db.add(src)
        db.flush()
        fpath = folder / "报告.pdf"
        fpath.write_bytes(b"%PDF-1.4 fake")
        item = InfoItem(source_id=src.id, external_id=str(fpath), title="报告.pdf", content="c")
        db.add(item)
        db.flush()
        fd = _figs_dir()
        for i in range(2):
            fp = fd / f"fig_{item.id}_{i}.png"
            fp.write_bytes(b"\x89PNG\r\n\x1a\n fake")
            db.add(InfoItemFigure(item_id=item.id, figure_index=i, storage_path=str(fp), mime="image/png"))
        r = _make_result(db, src, item)
        atts = collect_attachments(db, [r])
    names = [a.filename for a in atts]
    assert "报告.pdf" in names
    assert sum(1 for n in names if n.endswith(".png")) == 2
    pdf_att = next(a for a in atts if a.filename == "报告.pdf")
    assert pdf_att.mime == "application/pdf"
    assert pdf_att.data == b"%PDF-1.4 fake"


def test_collect_aggregate_no_attachments(client):
    with SessionLocal() as db:
        src = InfoSource(name="s", type="local_folder", config={"folder_path": "/tmp"})
        db.add(src)
        db.flush()
        r = _make_result(db, src, None, result_type="aggregate")
        atts = collect_attachments(db, [r])
    assert atts == []


def test_collect_non_local_folder_no_file_attachment(client):
    with SessionLocal() as db:
        src = InfoSource(name="w", type="website", config={"url": "http://x"})
        db.add(src)
        db.flush()
        item = InfoItem(source_id=src.id, external_id="http://x/a.html", title="a", content="c")
        db.add(item)
        db.flush()
        r = _make_result(db, src, item)
        atts = collect_attachments(db, [r])
    assert atts == []  # website 无原文件、无图表


def test_collect_path_traversal_skipped(client):
    with SessionLocal() as db:
        folder = pathlib.Path(tempfile.mkdtemp())
        src = InfoSource(name="s", type="local_folder", config={"folder_path": str(folder)})
        db.add(src)
        db.flush()
        outside = pathlib.Path(tempfile.mkdtemp()) / "secret.pdf"
        outside.write_bytes(b"%PDF secret")
        item = InfoItem(source_id=src.id, external_id=str(outside), title="secret.pdf", content="c")
        db.add(item)
        db.flush()
        r = _make_result(db, src, item)
        atts = collect_attachments(db, [r])
    assert all(a.filename != "secret.pdf" for a in atts)


def test_collect_missing_file_skipped(client):
    with SessionLocal() as db:
        folder = pathlib.Path(tempfile.mkdtemp())
        src = InfoSource(name="s", type="local_folder", config={"folder_path": str(folder)})
        db.add(src)
        db.flush()
        item = InfoItem(
            source_id=src.id, external_id=str(folder / "notexist.pdf"),
            title="notexist.pdf", content="c",
        )
        db.add(item)
        db.flush()
        r = _make_result(db, src, item)
        atts = collect_attachments(db, [r])
    assert atts == []


def test_collect_size_limit_skipped(monkeypatch, client):
    import app.backend.services.push.attachments as att_mod

    monkeypatch.setattr(att_mod, "_MAX_ATTACHMENT_BYTES", 100)
    with SessionLocal() as db:
        folder = pathlib.Path(tempfile.mkdtemp())
        src = InfoSource(name="s", type="local_folder", config={"folder_path": str(folder)})
        db.add(src)
        db.flush()
        fpath = folder / "big.pdf"
        fpath.write_bytes(b"0" * 200)
        item = InfoItem(source_id=src.id, external_id=str(fpath), title="big.pdf", content="c")
        db.add(item)
        db.flush()
        r = _make_result(db, src, item)
        atts = collect_attachments(db, [r])
    assert all(a.filename != "big.pdf" for a in atts)


def test_collect_filename_is_basename(client):
    with SessionLocal() as db:
        folder = pathlib.Path(tempfile.mkdtemp())
        sub = folder / "sub"
        sub.mkdir()
        src = InfoSource(name="s", type="local_folder", config={"folder_path": str(folder)})
        db.add(src)
        db.flush()
        fpath = sub / "deep.pdf"
        fpath.write_bytes(b"%PDF")
        item = InfoItem(source_id=src.id, external_id=str(fpath), title="deep.pdf", content="c")
        db.add(item)
        db.flush()
        r = _make_result(db, src, item)
        atts = collect_attachments(db, [r])
    assert any(a.filename == "deep.pdf" for a in atts)
    assert all("/" not in a.filename and "\\" not in a.filename for a in atts)
