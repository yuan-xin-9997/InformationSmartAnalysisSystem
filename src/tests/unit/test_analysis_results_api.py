"""Analysis results API: per_item carries source_file, aggregate is null.

Covers spec scenario "分析结果接口携带来源文件信息":
- per_item 结果携带文件名/路径/标题/作者/作者单位/发布时间/页数/图表列表
- aggregate 结果 source_file 为 null
- 单次 results 接口调用即可获得全部信息（无需额外逐条请求）
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.backend.core.database import SessionLocal
from app.backend.models.analysis import AnalysisResult, AnalysisTask
from app.backend.models.info_source import InfoItem, InfoItemFigure, InfoSource
from app.backend.models.task import TaskRun


def _seed(db) -> tuple[int, int]:
    """Create source + item(with metadata + 2 figures) + task + run + 2 results.

    Returns (task_id, run_id).
    """
    src = InfoSource(name="src-1", type="local_folder", config={})
    db.add(src)
    db.commit()
    db.refresh(src)

    item = InfoItem(
        source_id=src.id,
        external_id="/abs/path/report.pdf",
        title="季度报告.pdf",
        url="/abs/path/report.pdf",
        content="正文内容",
        author="张三",
        author_affiliation="某研究院",
        article_published_at=datetime(2026, 1, 15, 3, 30, tzinfo=timezone.utc),
        page_count=7,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    fig0 = InfoItemFigure(
        item_id=item.id,
        figure_index=0,
        storage_path="data/figures/item-1/fig-0.png",
        mime="image/png",
        width=800,
        height=600,
        caption="图一",
    )
    fig1 = InfoItemFigure(
        item_id=item.id,
        figure_index=1,
        storage_path="data/figures/item-1/fig-1.png",
        mime="image/png",
        width=1024,
        height=768,
        caption=None,
    )
    db.add_all([fig0, fig1])
    db.commit()

    task = AnalysisTask(name="t-1", description="", config={"mode": "per_item"})
    db.add(task)
    db.commit()
    db.refresh(task)

    run = TaskRun(
        kind="analysis",
        ref_id=task.id,
        ref_name=task.name,
        mode="incremental",
        status="succeeded",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # per_item result tied to the item; aggregate result with no item.
    db.add(
        AnalysisResult(
            task_run_id=run.id,
            task_id=task.id,
            source_id=src.id,
            info_item_id=item.id,
            result_type="per_item",
            content="这是 per_item 分析结论。",
        )
    )
    db.add(
        AnalysisResult(
            task_run_id=run.id,
            task_id=task.id,
            source_id=src.id,
            info_item_id=None,
            result_type="aggregate",
            content="这是 aggregate 汇总结论。",
        )
    )
    db.commit()
    return task.id, run.id


def test_per_item_result_carries_source_file(client, admin_headers):
    """per_item 结果的 source_file 含文件名/路径/元数据/图表列表。"""
    with SessionLocal() as db:
        task_id, run_id = _seed(db)

    r = client.get(
        f"/api/analysis-tasks/{task_id}/results?run_id={run_id}",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 2

    # 结果按 id desc 排序：aggregate(id 较大) 在前，per_item 在后。
    by_type = {d["result_type"]: d for d in data}
    assert "per_item" in by_type and "aggregate" in by_type

    per = by_type["per_item"]
    sf = per["source_file"]
    assert sf is not None, "per_item 结果必须有 source_file"
    assert sf["filename"] == "季度报告.pdf"
    assert sf["file_path"] == "/abs/path/report.pdf"
    assert sf["title"] == "季度报告.pdf"
    assert sf["author"] == "张三"
    assert sf["author_affiliation"] == "某研究院"
    assert sf["page_count"] == 7
    # published_at 序列化为北京时间 ISO 字符串（UTC 03:30 -> Beijing 11:30）
    assert sf["published_at"].startswith("2026-01-15T11:30")
    assert sf["file_url"] == f"/api/info-sources/{per['source_id']}/items/{per['info_item_id']}/file"

    figs = sf["figures"]
    assert len(figs) == 2
    assert figs[0]["index"] == 0
    assert figs[0]["url"] == f"/api/info-sources/{per['source_id']}/items/{per['info_item_id']}/figures/0"
    assert figs[0]["mime"] == "image/png"
    assert figs[0]["width"] == 800
    assert figs[0]["height"] == 600
    assert figs[1]["index"] == 1
    assert figs[1]["url"] == f"/api/info-sources/{per['source_id']}/items/{per['info_item_id']}/figures/1"
    assert figs[1]["width"] == 1024


def test_aggregate_result_source_file_is_null(client, admin_headers):
    """aggregate 结果的 source_file 必须为 null。"""
    with SessionLocal() as db:
        task_id, run_id = _seed(db)

    r = client.get(
        f"/api/analysis-tasks/{task_id}/results?run_id={run_id}",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    by_type = {d["result_type"]: d for d in r.json()}
    assert by_type["aggregate"]["source_file"] is None
    assert by_type["aggregate"]["info_item_id"] is None


def test_single_call_returns_all_three_segments(client, admin_headers):
    """一次 results 接口调用即可获得文件信息、元数据、图表与分析文本。"""
    with SessionLocal() as db:
        task_id, run_id = _seed(db)

    r = client.get(
        f"/api/analysis-tasks/{task_id}/results?run_id={run_id}",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    # 单次请求即返回 per_item + aggregate，且 per_item 含完整 source_file
    by_type = {d["result_type"]: d for d in r.json()}
    assert "per_item" in by_type and "aggregate" in by_type
    sf = by_type["per_item"]["source_file"]
    assert sf is not None
    assert sf["filename"]
    assert sf["file_path"]
    assert sf["title"]
    assert len(sf["figures"]) == 2
    assert by_type["per_item"]["content"]


def test_schema_serialization_per_item_and_aggregate():
    """纯 schema 序列化：AnalysisResultOut.source_file 可携带 SourceFileOut，aggregate 为 None。"""
    from app.backend.schemas.analysis import AnalysisResultOut
    from app.backend.schemas.info_source import InfoItemFigureOut, SourceFileOut

    sf = SourceFileOut(
        filename="doc.pdf",
        file_path="/abs/path/doc.pdf",
        title="doc.pdf",
        author="李四",
        author_affiliation="某大学",
        published_at=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
        page_count=3,
        file_url="/api/info-sources/1/items/1/file",
        figures=[
            InfoItemFigureOut(index=0, url="/api/info-sources/1/items/1/figures/0", mime="image/png", width=10, height=20),
        ],
    )
    per = AnalysisResultOut(
        id=1,
        task_run_id=1,
        task_id=1,
        source_id=1,
        source_name="s",
        info_item_id=1,
        result_type="per_item",
        content="x",
        created_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        source_file=sf,
    )
    dumped = per.model_dump(mode="json")
    assert dumped["source_file"] is not None
    assert dumped["source_file"]["filename"] == "doc.pdf"
    assert dumped["source_file"]["figures"][0]["index"] == 0
    assert dumped["source_file"]["published_at"].startswith("2026-02-01T08:00")  # UTC 00:00 -> Beijing 08:00

    agg = AnalysisResultOut(
        id=2,
        task_run_id=1,
        task_id=1,
        source_id=1,
        source_name="s",
        info_item_id=None,
        result_type="aggregate",
        content="y",
        created_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        source_file=None,
    )
    dumped_agg = agg.model_dump(mode="json")
    assert dumped_agg["source_file"] is None
