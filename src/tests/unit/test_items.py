"""Info-item list/count/pagination tests."""
from __future__ import annotations

import pathlib
import tempfile
from datetime import datetime


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


# ---- 选择条目弹窗增强：ids / exclude_ids / sort_by / order / keyword ----


def _seed_items(rows):
    """直接写库播种条目。rows: list[(title, analyzed, published_at)]。返回 (source_id, [item_id])。"""
    from app.backend.core.database import SessionLocal
    from app.backend.models.info_source import InfoItem, InfoSource

    db = SessionLocal()
    try:
        src = InfoSource(name="query-test", type="local_folder", config={})
        db.add(src)
        db.commit()
        db.refresh(src)
        ids = []
        for i, (title, analyzed, pub) in enumerate(rows):
            it = InfoItem(
                source_id=src.id,
                external_id=f"ext-{i}",
                title=title,
                analyzed=analyzed,
                published_at=pub,
            )
            db.add(it)
            db.commit()
            db.refresh(it)
            ids.append(it.id)
        return src.id, ids
    finally:
        db.close()


def _query(client, headers, body):
    return client.post(
        "/api/info-sources/items/query", headers=headers, json=body
    ).json()


def test_items_query_request_defaults():
    """ItemsQueryRequest 新字段默认值与向后兼容。"""
    from app.backend.schemas.info_source import ItemsQueryRequest

    r = ItemsQueryRequest(source_ids=[1])
    assert r.ids is None and r.exclude_ids is None and r.sort_by is None
    assert r.order == "desc" and r.keyword is None
    # 旧 payload（不带新字段）仍可解析
    r2 = ItemsQueryRequest(source_ids=[1], limit=10, offset=0, analyzed=True)
    assert r2.analyzed is True and r2.order == "desc"


def test_items_query_by_ids(client, admin_headers):
    sid, ids = _seed_items([("a", False, None), ("b", False, None), ("c", False, None)])
    r = _query(client, admin_headers, {"source_ids": [sid], "ids": [ids[0], ids[2]]})
    assert r["total"] == 2
    assert {it["id"] for it in r["items"]} == {ids[0], ids[2]}


def test_items_query_exclude_ids(client, admin_headers):
    sid, ids = _seed_items([("a", False, None), ("b", False, None), ("c", False, None)])
    r = _query(
        client, admin_headers, {"source_ids": [sid], "exclude_ids": [ids[0], ids[2]]}
    )
    assert r["total"] == 1
    assert [it["id"] for it in r["items"]] == [ids[1]]


def test_items_query_sort_by_title(client, admin_headers):
    sid, _ = _seed_items(
        [("banana", False, None), ("apple", False, None), ("cherry", False, None)]
    )
    asc = _query(
        client, admin_headers, {"source_ids": [sid], "sort_by": "title", "order": "asc"}
    )
    assert [it["title"] for it in asc["items"]] == ["apple", "banana", "cherry"]
    desc = _query(
        client, admin_headers, {"source_ids": [sid], "sort_by": "title", "order": "desc"}
    )
    assert [it["title"] for it in desc["items"]] == ["cherry", "banana", "apple"]


def test_items_query_sort_by_published_at(client, admin_headers):
    sid, _ = _seed_items(
        [
            ("c", False, datetime(2026, 3, 1)),
            ("a", False, datetime(2026, 1, 1)),
            ("b", False, datetime(2026, 2, 1)),
        ]
    )
    asc = _query(
        client,
        admin_headers,
        {"source_ids": [sid], "sort_by": "published_at", "order": "asc"},
    )
    assert [it["title"] for it in asc["items"]] == ["a", "b", "c"]


def test_items_query_sort_by_analyzed(client, admin_headers):
    sid, _ = _seed_items(
        [("t1", True, None), ("t2", False, None), ("t3", True, None), ("t4", False, None)]
    )
    asc = _query(
        client, admin_headers, {"source_ids": [sid], "sort_by": "analyzed", "order": "asc"}
    )
    seq = [it["analyzed"] for it in asc["items"]]
    assert seq == sorted(seq)  # False(0) 在前、True(1) 在后
    assert seq[0] is False and seq[-1] is True


def test_items_query_keyword(client, admin_headers):
    sid, _ = _seed_items(
        [("Apple report", False, None), ("Banana", False, None), ("apple pie", False, None)]
    )
    r = _query(client, admin_headers, {"source_ids": [sid], "keyword": "apple"})
    assert {it["title"] for it in r["items"]} == {"Apple report", "apple pie"}


def test_items_query_unknown_sort_falls_back(client, admin_headers):
    sid, ids = _seed_items([("a", False, None), ("b", False, None), ("c", False, None)])
    r = _query(
        client, admin_headers, {"source_ids": [sid], "sort_by": "password", "order": "asc"}
    )
    # 非白名单字段回退默认 id 倒序，不报错
    assert [it["id"] for it in r["items"]] == list(reversed(ids))


def test_items_query_injection_safe(client, admin_headers):
    sid, _ = _seed_items([("a", False, None), ("b", False, None)])
    r = _query(
        client,
        admin_headers,
        {"source_ids": [sid], "sort_by": "title; DROP TABLE info_items;--"},
    )
    assert r["total"] == 2  # 无报错、表完好
    r2 = _query(client, admin_headers, {"source_ids": [sid]})
    assert r2["total"] == 2  # 表仍可查


def test_items_query_backward_compat(client, admin_headers):
    sid, ids = _seed_items([("a", False, None), ("b", False, None), ("c", False, None)])
    r = _query(client, admin_headers, {"source_ids": [sid], "limit": 10, "offset": 0})
    assert [it["id"] for it in r["items"]] == list(reversed(ids))  # id 倒序，与现状一致


def test_items_query_analyzed_full_page(client, admin_headers):
    """analyzed 过滤在 SQL 层生效，每页满额返回（修复取行后 Python 二次过滤缺陷）。"""
    rows = [
        ("t1", True, None),
        ("t2", False, None),
        ("t3", True, None),
        ("t4", False, None),
        ("t5", True, None),
    ]
    sid, _ = _seed_items(rows)
    r = _query(
        client, admin_headers, {"source_ids": [sid], "analyzed": True, "limit": 2, "offset": 0}
    )
    assert r["total"] == 3
    assert len(r["items"]) == 2  # 旧代码此处返回 1（Python 后过滤剔除非已分析）
    assert all(it["analyzed"] is True for it in r["items"])


def test_items_query_combined(client, admin_headers):
    rows = [
        ("apple a", True, None),
        ("apple b", False, None),
        ("banana", True, None),
    ]
    sid, _ = _seed_items(rows)
    r = _query(
        client,
        admin_headers,
        {
            "source_ids": [sid],
            "keyword": "apple",
            "analyzed": True,
            "sort_by": "title",
            "order": "asc",
        },
    )
    assert [it["title"] for it in r["items"]] == ["apple a"]
