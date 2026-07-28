"""TDD tests for file preview / figure serving / reextract APIs (task 4).

Covers spec scenarios "源文件与图表的安全访问与预览":
- PDF inline preview, docx download, html/txt/md as text/plain (not text/html)
- Figure image bytes served by index with correct MIME
- Path traversal / cross-source access -> 403/404 (no file read)
- Disk file missing -> explicit 404 (not silent)
- POST reextract -> 200 dict; missing file -> 404
- Permission separation: analysis_tasks grants file/figures; info_sources grants reextract
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest


# ---------- helpers ----------


def _make_png(width: int = 2, height: int = 2, color: tuple = (255, 0, 0)) -> bytes:
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


def _make_pdf(path: Path, title: str = "T") -> None:
    import fitz

    doc = fitz.open()
    doc.set_metadata({"title": title})
    doc.new_page()
    doc.save(str(path))
    doc.close()


def _make_docx(path: Path, title: str = "T") -> None:
    from docx import Document

    doc = Document()
    doc.add_paragraph("body text")
    doc.core_properties.title = title
    doc.save(str(path))


def _seed_source(db, folder: Path, name: str = "s", stype: str = "local_folder") -> int:
    from app.backend.models.info_source import InfoSource

    config = {"folder_path": str(folder)} if stype == "local_folder" else {}
    src = InfoSource(name=name, type=stype, config=config)
    db.add(src)
    db.commit()
    db.refresh(src)
    return src.id


def _seed_item(db, source_id: int, external_id: str, title: str = "t") -> int:
    from app.backend.models.info_source import InfoItem

    item = InfoItem(
        source_id=source_id, external_id=external_id, title=title, content="c"
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item.id


def _seed_figure(
    db,
    item_id: int,
    storage_path: str,
    mime: str = "image/png",
    index: int = 0,
) -> int:
    from app.backend.models.info_source import InfoItemFigure

    fig = InfoItemFigure(
        item_id=item_id,
        figure_index=index,
        storage_path=storage_path,
        mime=mime,
    )
    db.add(fig)
    db.commit()
    db.refresh(fig)
    return fig.id


def _new_session():
    from app.backend.core.database import SessionLocal

    return SessionLocal()


# ---------- GET file: happy paths ----------


def test_get_file_pdf_inline(client, admin_headers, tmp_path):
    """PDF: 200, Content-Disposition inline, media_type application/pdf."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "report.pdf"
    _make_pdf(pdf, title="My Report")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="report.pdf")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    cd = r.headers.get("content-disposition", "")
    assert "inline" in cd


def test_get_file_docx_attachment(client, admin_headers, tmp_path):
    """docx: 200, Content-Disposition attachment (download)."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    docx = folder / "doc.docx"
    _make_docx(docx, title="Doc Title")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(docx.resolve()), title="doc.docx")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert (
        r.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd


def test_get_file_txt_plain(client, admin_headers, tmp_path):
    """txt: 200, text/plain (not text/html)."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    txt = folder / "note.txt"
    txt.write_text("hello world", encoding="utf-8")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(txt.resolve()), title="note.txt")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert "hello world" in r.text


def test_get_file_md_plain(client, admin_headers, tmp_path):
    """md: 200, text/plain."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    md = folder / "readme.md"
    md.write_text("# Title\nbody", encoding="utf-8")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(md.resolve()), title="readme.md")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")


def test_get_file_html_served_as_text_plain(client, admin_headers, tmp_path):
    """html: 200, text/plain (NOT text/html -- XSS protection)."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    html = folder / "page.html"
    html.write_text("<html><body><script>alert(1)</script></body></html>", encoding="utf-8")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(html.resolve()), title="page.html")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    # Must NOT be served as text/html (would allow browser to render/execute)
    assert not r.headers["content-type"].startswith("text/html")
    assert r.headers["content-type"].startswith("text/plain")


# ---------- GET file: security / error paths ----------


def test_get_file_cross_source_404(client, admin_headers, tmp_path):
    """item exists but belongs to a different source -> 404."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "a.pdf"
    _make_pdf(pdf)

    with SessionLocal() as db:
        src_a = _seed_source(db, folder, name="a")
        src_b = _seed_source(db, folder, name="b")
        # item belongs to src_a
        item_id = _seed_item(db, src_a, str(pdf.resolve()), title="a.pdf")

    # request via src_b's id
    r = client.get(
        f"/api/info-sources/{src_b}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 404


def test_get_file_path_traversal_403(client, admin_headers, tmp_path):
    """external_id points to a file OUTSIDE folder_path -> 403 (no read)."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    # "outside.pdf" is a sibling of folder/, i.e. outside folder_path
    outside = tmp_path / "outside.pdf"
    _make_pdf(outside)

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(outside.resolve()), title="outside.pdf")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 403, r.text


def test_get_file_missing_on_disk_404(client, admin_headers, tmp_path):
    """item exists but the file was deleted from disk -> 404."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "gone.pdf"
    _make_pdf(pdf)

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="gone.pdf")

    # delete the file after seeding
    pdf.unlink()

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 404


def test_get_file_unsupported_type_404(client, admin_headers, tmp_path):
    """Unsupported suffix (e.g. .xlsx) -> 404."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    xlsx = folder / "data.xlsx"
    xlsx.write_bytes(b"fake xlsx content")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(xlsx.resolve()), title="data.xlsx")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 404


def test_get_file_non_local_folder_source_404(client, admin_headers, tmp_path):
    """Source type != local_folder (e.g. website) -> 404."""
    from app.backend.core.database import SessionLocal

    with SessionLocal() as db:
        src_id = _seed_source(db, tmp_path, stype="website")
        item_id = _seed_item(db, src_id, "https://example.com/a.pdf", title="a.pdf")

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 404


def test_get_file_item_not_found_404(client, admin_headers, tmp_path):
    """item_id does not exist -> 404."""
    from app.backend.core.database import SessionLocal

    with SessionLocal() as db:
        src_id = _seed_source(db, tmp_path)

    r = client.get(
        f"/api/info-sources/{src_id}/items/999999/file", headers=admin_headers
    )
    assert r.status_code == 404


def test_get_file_missing_folder_path_config_404(client, admin_headers, tmp_path):
    """local_folder source whose config lacks folder_path -> 404 (not 500). (I-6)"""
    from app.backend.core.database import SessionLocal
    from app.backend.models.info_source import InfoItem, InfoSource

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "a.pdf"
    _make_pdf(pdf)

    with SessionLocal() as db:
        src = InfoSource(name="s", type="local_folder", config={})  # no folder_path
        db.add(src)
        db.commit()
        db.refresh(src)
        src_id = src.id
        item = InfoItem(
            source_id=src_id, external_id=str(pdf.resolve()), title="a.pdf", content="c"
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=admin_headers
    )
    assert r.status_code == 404, r.text
    assert "folder_path" in r.text


def test_get_file_without_auth_401(client, tmp_path):
    """No token -> 401."""
    r = client.get("/api/info-sources/1/items/1/file")
    assert r.status_code == 401


# ---------- GET figures: happy + error paths ----------


def test_get_figure_by_index(client, admin_headers, tmp_path):
    """GET figures/{index}: 200 + correct bytes for each of multiple figures.

    Seeds two figures (index 0 and 1) with distinct bytes and asserts each
    endpoint returns its own bytes -- proving index alignment (I-4).
    """
    from app.backend.core.config import settings
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf)

    fig_dir = settings.figures_dir / "2026/01/01"
    fig_dir.mkdir(parents=True, exist_ok=True)
    # two distinct figures so the served bytes can be told apart by index
    fig0_bytes = _make_png(3, 4, color=(255, 0, 0))
    fig1_bytes = _make_png(5, 6, color=(0, 0, 255))
    assert fig0_bytes != fig1_bytes  # sanity
    fig0 = fig_dir / "1_0.png"
    fig1 = fig_dir / "1_1.png"
    fig0.write_bytes(fig0_bytes)
    fig1.write_bytes(fig1_bytes)

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="doc.pdf")
        _seed_figure(db, item_id, str(fig0.resolve()), mime="image/png", index=0)
        _seed_figure(db, item_id, str(fig1.resolve()), mime="image/png", index=1)

    # figure 0
    r0 = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/figures/0",
        headers=admin_headers,
    )
    assert r0.status_code == 200, r0.text
    assert r0.headers["content-type"] == "image/png"
    assert r0.content == fig0_bytes

    # figure 1 (distinct bytes -> proves index alignment, not always returning figure 0)
    r1 = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/figures/1",
        headers=admin_headers,
    )
    assert r1.status_code == 200, r1.text
    assert r1.headers["content-type"] == "image/png"
    assert r1.content == fig1_bytes
    assert r1.content != r0.content


def test_get_figure_nonexistent_index_404(client, admin_headers, tmp_path):
    """Index not present -> 404."""
    from app.backend.core.config import settings
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf)

    fig_dir = settings.figures_dir / "2026/01/01"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig_file = fig_dir / "2_0.png"
    fig_file.write_bytes(_make_png(3, 4))

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="doc.pdf")
        _seed_figure(db, item_id, str(fig_file.resolve()), mime="image/png", index=0)

    # index 1 doesn't exist
    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/figures/1",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_get_figure_cross_source_404(client, admin_headers, tmp_path):
    """Figure's item belongs to a different source -> 404."""
    from app.backend.core.config import settings
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf)

    fig_dir = settings.figures_dir / "2026/01/01"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig_file = fig_dir / "3_0.png"
    fig_file.write_bytes(_make_png(3, 4))

    with SessionLocal() as db:
        src_a = _seed_source(db, folder, name="a")
        src_b = _seed_source(db, folder, name="b")
        item_id = _seed_item(db, src_a, str(pdf.resolve()), title="doc.pdf")
        _seed_figure(db, item_id, str(fig_file.resolve()), mime="image/png", index=0)

    # request via src_b (wrong source)
    r = client.get(
        f"/api/info-sources/{src_b}/items/{item_id}/figures/0",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_get_figure_path_traversal_403(client, admin_headers, tmp_path):
    """storage_path points outside figures_dir -> 403 (no read)."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf)

    # a PNG file that exists but is OUTSIDE settings.figures_dir
    outside = tmp_path / "sneaky.png"
    outside.write_bytes(_make_png(1, 1))

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="doc.pdf")
        _seed_figure(db, item_id, str(outside.resolve()), mime="image/png", index=0)

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/figures/0",
        headers=admin_headers,
    )
    assert r.status_code == 403, r.text


def test_get_figure_missing_on_disk_404(client, admin_headers, tmp_path):
    """Figure row exists but file was deleted -> 404."""
    from app.backend.core.config import settings
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf)

    fig_dir = settings.figures_dir / "2026/01/01"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig_file = fig_dir / "4_0.png"
    fig_file.write_bytes(_make_png(3, 4))

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="doc.pdf")
        _seed_figure(db, item_id, str(fig_file.resolve()), mime="image/png", index=0)

    # delete the figure file
    fig_file.unlink()

    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/figures/0",
        headers=admin_headers,
    )
    assert r.status_code == 404


# ---------- POST reextract ----------


def test_reextract_success(client, admin_headers, tmp_path):
    """POST reextract: 200, returns dict with item_id + updated."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf, title="Reextracted Title")

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="old-title")

    r = client.post(
        f"/api/info-sources/{src_id}/items/{item_id}/reextract",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["item_id"] == item_id
    assert data["updated"] is True


def test_reextract_missing_file_404(client, admin_headers, tmp_path):
    """File gone -> reextract_item raises ValueError -> 404."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(
            db, src_id, str(folder / "gone.pdf"), title="gone.pdf"
        )

    r = client.post(
        f"/api/info-sources/{src_id}/items/{item_id}/reextract",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_reextract_cross_source_404(client, admin_headers, tmp_path):
    """item doesn't belong to the given source -> 404."""
    from app.backend.core.database import SessionLocal

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "doc.pdf"
    _make_pdf(pdf)

    with SessionLocal() as db:
        src_a = _seed_source(db, folder, name="a")
        src_b = _seed_source(db, folder, name="b")
        item_id = _seed_item(db, src_a, str(pdf.resolve()), title="doc.pdf")

    r = client.post(
        f"/api/info-sources/{src_b}/items/{item_id}/reextract",
        headers=admin_headers,
    )
    assert r.status_code == 404


# ---------- permission separation ----------


def test_file_requires_analysis_tasks_permission(client, tmp_path):
    """User without analysis_tasks page permission -> 403 on GET file."""
    from app.backend.core.database import SessionLocal
    from app.backend.models.user import PagePermission, User

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "a.pdf"
    _make_pdf(pdf)

    # login as tester (regular user, no page permissions)
    r = client.post(
        "/api/auth/login", json={"username": "tester", "password": "tester123"}
    )
    assert r.status_code == 200
    tester_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="a.pdf")

    # tester has NO page permissions -> 403
    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=tester_headers
    )
    assert r.status_code == 403


def test_reextract_requires_info_sources_not_analysis_tasks(client, tmp_path):
    """User with only analysis_tasks (not info_sources) -> 200 on file, 403 on reextract."""
    from app.backend.core.database import SessionLocal
    from app.backend.models.user import PagePermission, User

    folder = tmp_path / "folder"
    folder.mkdir()
    pdf = folder / "a.pdf"
    _make_pdf(pdf, title="T")

    # login as tester
    r = client.post(
        "/api/auth/login", json={"username": "tester", "password": "tester123"}
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    tester_headers = {"Authorization": f"Bearer {token}"}

    with SessionLocal() as db:
        src_id = _seed_source(db, folder)
        item_id = _seed_item(db, src_id, str(pdf.resolve()), title="a.pdf")
        # grant tester only analysis_tasks (not info_sources)
        tester = db.query(User).filter(User.username == "tester").first()
        assert tester is not None
        db.add(PagePermission(user_id=tester.id, page_key="analysis_tasks"))
        db.commit()

    # GET file should succeed (analysis_tasks granted)
    r = client.get(
        f"/api/info-sources/{src_id}/items/{item_id}/file", headers=tester_headers
    )
    assert r.status_code == 200, r.text

    # POST reextract should be forbidden (info_sources NOT granted)
    r = client.post(
        f"/api/info-sources/{src_id}/items/{item_id}/reextract",
        headers=tester_headers,
    )
    assert r.status_code == 403
