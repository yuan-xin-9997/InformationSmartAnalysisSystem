"""Analysis engine unit tests: selection_strategy (sequential / newest_unanalyzed)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.backend.core.database import SessionLocal
from app.backend.models.analysis import AnalysisResult, AnalysisTask, TaskSource
from app.backend.models.info_source import InfoItem, InfoSource
from app.backend.models.task import TaskRun
from app.backend.services.analysis import run_analysis


@pytest.fixture(autouse=True)
def _noop_push(monkeypatch):
    """隔离推送钩子，避免分析成功后触发推送副作用干扰断言。"""
    from app.backend.services.analysis import engine

    monkeypatch.setattr(engine, "on_analysis_completed", lambda tid: None)


def _dt(month, day, hour=0):
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


def _build(
    items_spec,
    *,
    selection_strategy=None,
    max_per=50,
    analysis_mode="per_item",
    task_mode="incremental",
    watermark_idx=None,
):
    """直接在 DB 构造 source/items/task/task_source/run。

    items_spec: list[dict]，支持的键 title/published_at/article_published_at/fetched_at/analyzed。
    返回 (task_id, run_id, item_ids)。
    """
    with SessionLocal() as db:
        src = InfoSource(name="s", type="local_folder", config={})
        db.add(src)
        db.flush()
        item_ids = []
        for i, spec in enumerate(items_spec):
            it = InfoItem(
                source_id=src.id,
                external_id=f"ext{i}",
                title=spec.get("title", f"t{i}"),
                content=spec.get("content", f"c{i}"),
                published_at=spec.get("published_at"),
                article_published_at=spec.get("article_published_at"),
                fetched_at=spec.get("fetched_at", _dt(7, 1)),
                analyzed=spec.get("analyzed", False),
            )
            db.add(it)
            db.flush()
            item_ids.append(it.id)
        cfg = {"mode": analysis_mode, "max_items_per_source": max_per}
        if selection_strategy is not None:
            cfg["selection_strategy"] = selection_strategy
        task = AnalysisTask(name="t", config=cfg)
        db.add(task)
        db.flush()
        ts = TaskSource(task_id=task.id, source_id=src.id)
        if watermark_idx is not None:
            ts.last_analyzed_item_id = item_ids[watermark_idx]
        db.add(ts)
        run = TaskRun(
            kind="analysis", ref_id=task.id, ref_name="t", mode=task_mode, status="pending"
        )
        db.add(run)
        db.flush()
        db.commit()
        return task.id, run.id, item_ids


def _analyzed_item_ids(task_id):
    with SessionLocal() as db:
        rows = db.query(AnalysisResult).filter(AnalysisResult.task_id == task_id).all()
        return sorted(r.info_item_id for r in rows if r.info_item_id is not None)


def _analyzed_item_ids_in_order(task_id):
    """按分析先后顺序（AnalysisResult.id 升序）返回 info_item_id。"""
    with SessionLocal() as db:
        rows = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.task_id == task_id,
                AnalysisResult.info_item_id.isnot(None),
            )
            .order_by(AnalysisResult.id.asc())
            .all()
        )
        return [r.info_item_id for r in rows]


def _watermark(task_id):
    with SessionLocal() as db:
        ts = db.query(TaskSource).filter(TaskSource.task_id == task_id).one()
        return ts.last_analyzed_item_id, ts.last_analyzed_at


def _new_run(task_id, mode="incremental"):
    with SessionLocal() as db:
        run = TaskRun(
            kind="analysis", ref_id=task_id, ref_name="t", mode=mode, status="pending"
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id


# --- 1.1 默认 sequential 回归 ---


def test_default_strategy_sequential_incremental_watermark(client, mock_llm):
    """未指定 selection_strategy -> sequential：增量按 id>水位线升序取，并推进水位线。"""
    task_id, run_id, ids = _build(
        [{"title": "a"}, {"title": "b"}, {"title": "c"}],
        watermark_idx=0,
    )
    run_analysis(run_id, task_id, "incremental")
    assert _analyzed_item_ids(task_id) == sorted([ids[1], ids[2]])
    wm, wm_at = _watermark(task_id)
    assert wm == max(ids[1], ids[2])
    assert wm_at is not None


def test_default_strategy_sequential_full_takes_all(client, mock_llm):
    """sequential 全量取该源全部（受 max_per 限制），不依水位线。"""
    task_id, run_id, ids = _build(
        [{"title": "a"}, {"title": "b"}, {"title": "c"}],
        max_per=50,
        watermark_idx=2,
    )
    run_analysis(run_id, task_id, "full")
    assert _analyzed_item_ids(task_id) == sorted(ids)


# --- 1.2 newest_unanalyzed 选最新未分析篇、跳过已分析 ---


def test_newest_unanalyzed_picks_latest_and_skips_analyzed(client, mock_llm):
    task_id, run_id, ids = _build(
        [
            {"title": "A", "published_at": _dt(7, 28), "analyzed": False},
            {"title": "B", "published_at": _dt(7, 29), "analyzed": False},
            {"title": "C", "published_at": _dt(7, 30), "analyzed": True},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=1,
    )
    run_analysis(run_id, task_id, "incremental")
    # 未分析中最新为 B(7/29)；C 已分析被跳过
    assert _analyzed_item_ids(task_id) == [ids[1]]


# --- 1.3 时间键优先级 published_at -> article_published_at -> fetched_at，平局 id 降序 ---


def test_newest_unanalyzed_prefers_published_over_article(client, mock_llm):
    """published_at 优先于 article_published_at：X 的 article(7/31) 更新但应被忽略，用 published(7/28)。"""
    task_id, run_id, ids = _build(
        [
            {"title": "X", "published_at": _dt(7, 28), "article_published_at": _dt(7, 31)},
            {"title": "Y", "published_at": _dt(7, 30)},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=1,
    )
    run_analysis(run_id, task_id, "incremental")
    # 用 published_at: Y(7/30) > X(7/28) -> 选 Y；若误用 article 则 X(7/31) 被选
    assert _analyzed_item_ids(task_id) == [ids[1]]


def test_newest_unanalyzed_time_key_fallback_chain(client, mock_llm):
    """published_at -> article_published_at -> fetched_at 回退链，并按时间键倒序。"""
    task_id, run_id, ids = _build(
        [
            # R: 仅 fetched=7/28（id 最小、时间最小）
            {"title": "R", "published_at": None, "article_published_at": None, "fetched_at": _dt(7, 28)},
            # Q: 无 published，回退 article=7/29
            {"title": "Q", "published_at": None, "article_published_at": _dt(7, 29)},
            # P: published=7/30（id 最大、时间最大）
            {"title": "P", "published_at": _dt(7, 30)},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=3,
    )
    run_analysis(run_id, task_id, "incremental")
    # 倒序：P(7/30) -> Q(7/29) -> R(7/28)；id 顺序相反，可区分 sequential
    assert _analyzed_item_ids_in_order(task_id) == [ids[2], ids[1], ids[0]]


def test_newest_unanalyzed_tie_break_by_id_desc(client, mock_llm):
    task_id, run_id, ids = _build(
        [
            {"title": "first", "published_at": _dt(7, 28)},
            {"title": "second", "published_at": _dt(7, 28)},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=1,
    )
    run_analysis(run_id, task_id, "incremental")
    # 时间键相同 -> id 降序取较大者
    assert _analyzed_item_ids(task_id) == [max(ids)]


# --- 1.4 max_per 限制、多源独立、水位线不参与筛选、靠 analyzed 推进 ---


def test_newest_unanalyzed_respects_max_per(client, mock_llm):
    task_id, run_id, ids = _build(
        [
            {"published_at": _dt(7, 1)},
            {"published_at": _dt(7, 2)},
            {"published_at": _dt(7, 3)},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=2,
    )
    run_analysis(run_id, task_id, "incremental")
    # 取最新 2 篇：7/3, 7/2
    assert _analyzed_item_ids(task_id) == sorted([ids[2], ids[1]])


def test_newest_unanalyzed_ignores_watermark_for_filter(client, mock_llm):
    """水位线设为最大 id，但 newest_unanalyzed 不依水位线筛选，仍可选到未分析篇。"""
    task_id, run_id, ids = _build(
        [
            {"published_at": _dt(7, 1)},
            {"published_at": _dt(7, 2)},
            {"published_at": _dt(7, 3)},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=1,
        watermark_idx=2,
    )
    run_analysis(run_id, task_id, "incremental")
    # 仍选最新未分析 = 7/3
    assert _analyzed_item_ids(task_id) == [ids[2]]
    wm, _ = _watermark(task_id)
    assert wm == ids[2]


def test_newest_unanalyzed_advances_via_analyzed_flag(client, mock_llm):
    """第一次选最新 1 篇并标记 analyzed；第二次运行选下一篇最新未分析。"""
    task_id, run_id, ids = _build(
        [
            {"published_at": _dt(7, 1)},
            {"published_at": _dt(7, 2)},
            {"published_at": _dt(7, 3)},
        ],
        selection_strategy="newest_unanalyzed",
        max_per=1,
    )
    run_analysis(run_id, task_id, "incremental")
    assert _analyzed_item_ids(task_id) == [ids[2]]
    rid2 = _new_run(task_id)
    run_analysis(rid2, task_id, "incremental")
    assert _analyzed_item_ids(task_id) == sorted([ids[2], ids[1]])


# --- 1.5 未知值回退 sequential、custom 模式不受策略影响 ---


def test_unknown_strategy_falls_back_to_sequential(client, mock_llm):
    task_id, run_id, ids = _build(
        [{"title": "a"}, {"title": "b"}],
        selection_strategy="random",
        watermark_idx=0,
    )
    run_analysis(run_id, task_id, "incremental")
    # 回退 sequential：id > 水位线 -> 第 2 条
    assert _analyzed_item_ids(task_id) == [ids[1]]


def test_custom_mode_unaffected_by_selection_strategy(client, mock_llm):
    task_id, run_id, ids = _build(
        [{"title": "a"}, {"title": "b"}, {"title": "c"}],
        selection_strategy="newest_unanalyzed",
        analysis_mode="custom",
        task_mode="custom",
    )
    with SessionLocal() as db:
        t = db.get(AnalysisTask, task_id)
        t.config = {**t.config, "custom_item_ids": [ids[0], ids[2]]}
        db.commit()
    run_analysis(run_id, task_id, "custom")
    # custom 仍只分析指定条目，策略不改变候选集
    assert _analyzed_item_ids(task_id) == sorted([ids[0], ids[2]])
