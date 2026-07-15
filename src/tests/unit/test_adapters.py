"""Info-source adapter unit tests (no real network)."""
from __future__ import annotations


def test_local_folder_adapter(tmp_path):
    from app.backend.services.info_source.local_folder import LocalFolderAdapter

    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "b.md").write_text("# title\nbody text", encoding="utf-8")

    adapter = LocalFolderAdapter(
        {"folder_path": str(tmp_path), "patterns": ["*.txt", "*.md"]}
    )
    status = adapter.check_status()
    assert status.ok
    assert status.item_count == 2

    items = adapter.fetch_new_items()
    assert len(items) == 2
    titles = {it.title for it in items}
    assert titles == {"a.txt", "b.md"}
    assert all(it.content for it in items)


def test_local_folder_missing_path(tmp_path):
    from app.backend.services.info_source.local_folder import LocalFolderAdapter

    adapter = LocalFolderAdapter({"folder_path": str(tmp_path / "nope")})
    status = adapter.check_status()
    assert not status.ok


def test_local_folder_incremental_and_backfill(tmp_path):
    """已索引且未变更的文件跳过；新文件回补；顺序确定。"""
    from datetime import datetime, timezone

    from app.backend.services.info_source.local_folder import LocalFolderAdapter

    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B", encoding="utf-8")
    adapter = LocalFolderAdapter({"folder_path": str(tmp_path), "patterns": ["*.txt"]})

    # 首次同步：全部
    first = adapter.fetch_new_items()
    assert {it.title for it in first} == {"a.txt", "b.txt"}

    known = {it.external_id for it in first}
    since = datetime.now(timezone.utc)

    # 已知且未变更 -> 0
    assert adapter.fetch_new_items(since=since, known_ids=known) == []

    # 新文件回补（不在 known，无论 mtime）
    (tmp_path / "c.txt").write_text("C", encoding="utf-8")
    second = adapter.fetch_new_items(since=since, known_ids=known)
    assert [it.title for it in second] == ["c.txt"]


def test_website_adapter_with_mock_client():
    from app.backend.services.info_source.website import WebsiteAdapter

    listing_html = (
        '<html><body>'
        '<a class="art" href="/article/1">Article 1</a>'
        '<a class="art" href="http://example.com/article/2">Article 2</a>'
        '<a class="art" href="#">skip</a>'
        '</body></html>'
    )

    class MockClient:
        def fetch_html(self, url, mode="auto"):
            if url.endswith("/news"):
                return listing_html
            return f'<html><body><article><p>content of {url}</p></article></body></html>'

    adapter = WebsiteAdapter(
        {"url": "http://example.com/news", "link_selector": "a.art", "content_selector": "article"},
        web_fetch_client=MockClient(),
    )
    items = adapter.fetch_new_items()
    assert len(items) == 2
    assert all("content of" in it.content for it in items)
    urls = {it.url for it in items}
    assert "http://example.com/article/1" in urls
    assert "http://example.com/article/2" in urls


def test_freshrss_adapter_parsing(monkeypatch):
    from app.backend.services.info_source.freshrss import FreshRSSAdapter

    adapter = FreshRSSAdapter(
        {"base_url": "http://frss", "user": "u", "api_token": "t"}
    )
    monkeypatch.setattr(adapter, "_get_auth", lambda: "fakeauth")
    canned = {
        "items": [
            {
                "id": "item1",
                "title": "T1",
                "alternate": [{"href": "http://a/1"}],
                "content": {"content": "<p>body1</p>"},
                "published": 1735689600,
            },
            {
                "id": "item2",
                "title": "T2",
                "summary": {"content": "<p>body2</p>"},
                "published": 1735689660,
            },
        ]
    }
    monkeypatch.setattr(adapter, "_greader_get", lambda path, params=None: canned)

    items = adapter.fetch_new_items()
    assert len(items) == 2
    assert items[0].title == "T1"
    assert items[0].url == "http://a/1"
    assert "body1" in items[0].content
    assert items[1].published_at is not None
    assert "body2" in items[1].content


def test_factory_validates_config():
    import pytest

    from app.backend.services.info_source.factory import get_adapter, validate_config

    with pytest.raises(ValueError):
        validate_config("local_folder", {})
    with pytest.raises(ValueError):
        validate_config("unknown_type", {"x": 1})
    # valid
    ad = get_adapter("local_folder", {"folder_path": "/tmp"})
    assert ad.type == "local_folder"
