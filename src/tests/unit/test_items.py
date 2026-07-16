"""Info-item list/count/pagination tests."""
from __future__ import annotations

import pathlib
import tempfile


def _make_source(client, headers):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "a.txt").write_text("内容A", encoding="utf-8")
    (d / "b.txt").write_text("内容B", encoding="utf-8")
    sid = client.post(
        "/api/info-sources",
        headers=headers,
        json={
            "name": "items-test",
            "type": "local_folder",
            "config": {"folder_path": str(d), "patterns": ["*.txt"]},
        },
    ).json()["id"]
    client.post(f"/api/info-sources/{sid}/sync", headers=headers)
    return sid


def test_items_count_and_filter(client, admin_headers, sync_worker, mock_llm):
    sid = _make_source(client, admin_headers)

    c = client.get(f"/api/info-sources/{sid}/items/count", headers=admin_headers).json()
    assert c["all"] == 2 and c["total"] == 2
    assert c["analyzed"] == 0 and c["unanalyzed"] == 2

    # analyzed filter: nothing analyzed yet
    assert client.get(
        f"/api/info-sources/{sid}/items?analyzed=true", headers=admin_headers
    ).json() == []
    assert len(
        client.get(f"/api/info-sources/{sid}/items?analyzed=false", headers=admin_headers).json()
    ) == 2

    # count with filter
    cf = client.get(
        f"/api/info-sources/{sid}/items/count?analyzed=false", headers=admin_headers
    ).json()
    assert cf["total"] == 2 and cf["all"] == 2


def test_items_pagination(client, admin_headers, sync_worker, mock_llm):
    sid = _make_source(client, admin_headers)

    page1 = client.get(
        f"/api/info-sources/{sid}/items?limit=1&offset=0", headers=admin_headers
    ).json()
    page2 = client.get(
        f"/api/info-sources/{sid}/items?limit=1&offset=1", headers=admin_headers
    ).json()
    assert len(page1) == 1 and len(page2) == 1
    assert page1[0]["id"] != page2[0]["id"]  # 不同页不同条目


def test_items_query_across_sources(client, admin_headers, sync_worker, mock_llm):
    sid = _make_source(client, admin_headers)

    r = client.post(
        "/api/info-sources/items/query",
        headers=admin_headers,
        json={"source_ids": [sid], "limit": 10},
    ).json()
    assert r["total"] == 2 and len(r["items"]) == 2

    # 空 source_ids
    r2 = client.post(
        "/api/info-sources/items/query", headers=admin_headers, json={"source_ids": []}
    ).json()
    assert r2["total"] == 0 and r2["items"] == []

    # analyzed 过滤
    r3 = client.post(
        "/api/info-sources/items/query",
        headers=admin_headers,
        json={"source_ids": [sid], "analyzed": False},
    ).json()
    assert r3["total"] == 2
