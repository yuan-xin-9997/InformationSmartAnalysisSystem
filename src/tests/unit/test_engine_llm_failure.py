"""分析引擎对 LLM 输出失败的容错测试。

守护线上故障：推理模型因 ``max_tokens`` 过小返回空 content（``finish_reason="length"``），
旧实现把条目无条件判为成功、把运行置为 ``succeeded``、并触发推送钩子，最终发出一封
空正文邮件。本文件锁定三条不变量：

1. 失败的条目 MUST NOT 落库、MUST NOT 置 ``analyzed``、MUST NOT 推进水位线越过；
2. 运行摘要 MUST 显式暴露失败数量（不静默）；
3. 全部条目失败时运行状态为 ``failed``，且 **不触发推送**。

``LLMClient`` 侧的「空内容/截断判失败 + 截断翻倍重试」由
``tests/unit/test_llm_client.py`` 覆盖；这里只验证引擎的失败处理分支。
"""
from __future__ import annotations

import pathlib
import tempfile


def _make_folder_source(client, headers, files: dict[str, str]) -> int:
    d = pathlib.Path(tempfile.mkdtemp())
    for name, body in files.items():
        (d / name).write_text(body, encoding="utf-8")
    r = client.post(
        "/api/info-sources",
        headers=headers,
        json={
            "name": "s",
            "type": "local_folder",
            "config": {"folder_path": str(d), "patterns": ["*.txt"]},
        },
    )
    sid = r.json()["id"]
    client.post(f"/api/info-sources/{sid}/sync", headers=headers)
    return sid


def _make_task(client, headers, config: dict, source_ids: list[int]) -> int:
    return client.post(
        "/api/analysis-tasks",
        headers=headers,
        json={"name": "t", "config": config, "source_ids": source_ids},
    ).json()["id"]


def _run(client, headers, task_id: int, mode: str = "incremental") -> dict:
    r = client.post(
        f"/api/analysis-tasks/{task_id}/run", headers=headers, json={"mode": mode}
    )
    return client.get(
        f"/api/task-center/runs/{r.json()['run_id']}", headers=headers
    ).json()


def _failing_llm(monkeypatch, fail_markers: list[str]) -> list[str]:
    """替换 ``engine.LLMClient``：提示词命中任一标记即抛 ``LLMError``。

    返回该标记列表本身，测试可在中途 ``clear()`` 以模拟故障恢复。
    """
    import app.backend.services.analysis.engine as engine
    from app.backend.services.analysis.llm_client import LLMError

    class _LLM:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, system: str, user: str) -> str:
            for marker in fail_markers:
                if marker in user:
                    raise LLMError(f"模拟 LLM 失败（命中 {marker}）")
            return f"[分析] {user[:15]}"

    monkeypatch.setattr(engine, "LLMClient", _LLM)
    return fail_markers


def _db_state(task_id: int | None = None, source_id: int | None = None) -> dict:
    from app.backend.core.database import SessionLocal
    from app.backend.models.analysis import AnalysisResult, TaskSource
    from app.backend.models.info_source import InfoItem

    with SessionLocal() as db:
        results = (
            db.query(AnalysisResult).filter(AnalysisResult.task_id == task_id).all()
            if task_id is not None
            else []
        )
        q = db.query(InfoItem)
        if source_id is not None:
            q = q.filter(InfoItem.source_id == source_id)
        items = q.order_by(InfoItem.id.asc()).all()
        ts = (
            db.query(TaskSource).filter(TaskSource.task_id == task_id).first()
            if task_id is not None
            else None
        )
        return {
            "result_count": len(results),
            "result_item_ids": sorted(
                r.info_item_id for r in results if r.info_item_id is not None
            ),
            "item_ids": [i.id for i in items],
            "titles": {i.id: (i.title or "") for i in items},
            "analyzed": {i.id: i.analyzed for i in items},
            "watermark": ts.last_analyzed_item_id if ts else None,
        }


def _marker_for(state: dict, item_id: int) -> str:
    """条目的 LLM 提示词里包含文件名（``标题：<title>``），据此精准命中该条目。

    按真实 id 选失败条目，而非按文件名——目录扫描顺序不保证与文件名排序一致。
    """
    title = state["titles"][item_id]
    assert title, f"条目 #{item_id} 没有标题，无法构造失败标记"
    return title


# ---------- 部分失败：跳过该条目，其余照常完成 ----------


def test_partial_failure_skips_item_and_keeps_run_succeeded(
    client, admin_headers, sync_worker, monkeypatch
):
    """失败条目夹在批次中间：跳过它，其余照常完成，运行仍为 succeeded。"""
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B", "c.txt": "内容C"}
    )
    st0 = _db_state(None, sid)
    middle_id = sorted(st0["item_ids"])[1]  # 取中间那条，确保它不是最大 id
    _failing_llm(monkeypatch, [_marker_for(st0, middle_id)])
    tid = _make_task(client, admin_headers, {"mode": "per_item"}, [sid])

    run = _run(client, admin_headers, tid)
    assert run["status"] == "succeeded"
    assert "生成 2 条结果" in run["summary"]
    assert "失败 1 条" in run["summary"]

    st = _db_state(tid, sid)
    ok_ids = [i for i in st["item_ids"] if i != middle_id]

    # 失败条目：不落库、不置 analyzed
    assert st["result_item_ids"] == ok_ids
    assert st["analyzed"][middle_id] is False
    assert all(st["analyzed"][i] is True for i in ok_ids)
    # 水位线只按**成功**条目计算
    assert st["watermark"] == max(ok_ids)


def test_failure_logs_warning_with_item_id(client, admin_headers, sync_worker, monkeypatch):
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B"}
    )
    st0 = _db_state(None, sid)
    failed_id = min(st0["item_ids"])
    _failing_llm(monkeypatch, [_marker_for(st0, failed_id)])
    tid = _make_task(client, admin_headers, {"mode": "per_item"}, [sid])
    run = _run(client, admin_headers, tid)

    warnings = [log for log in run["logs"] if log["level"] == "WARNING"]
    assert any(f"条目#{failed_id}" in log["message"] for log in warnings), run["logs"]


def test_failure_on_trailing_item_is_retried_by_next_incremental_run(
    client, admin_headers, sync_worker, monkeypatch
):
    """失败集中在批次尾部时，水位线未越过它 → 下次增量会自动重跑。

    这正是「水位线只推进到成功条目」带来的收益：失败条目 id 大于水位线，
    下一次 ``sequential`` 增量会重新选中它。
    """
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B", "c.txt": "内容C"}
    )
    st0 = _db_state(None, sid)
    failed_id = max(st0["item_ids"])
    markers = _failing_llm(monkeypatch, [_marker_for(st0, failed_id)])
    tid = _make_task(client, admin_headers, {"mode": "per_item"}, [sid])

    run1 = _run(client, admin_headers, tid)
    assert run1["status"] == "succeeded"
    st = _db_state(tid, sid)
    assert st["analyzed"][failed_id] is False
    # 水位线严格小于失败条目 id —— 说明它被排除在水位线计算之外
    assert st["watermark"] == max(i for i in st["item_ids"] if i != failed_id)
    assert st["watermark"] < failed_id

    # 故障恢复后重跑增量：只重新分析失败的那一条
    markers.clear()
    run2 = _run(client, admin_headers, tid)
    assert run2["status"] == "succeeded"
    assert "处理 1 条" in run2["summary"]

    st2 = _db_state(tid, sid)
    assert st2["analyzed"][failed_id] is True
    assert st2["result_item_ids"].count(failed_id) == 1


# ---------- 全部失败：运行判失败且不推送 ----------


def test_all_items_fail_marks_run_failed_and_does_not_push(
    client, admin_headers, sync_worker, monkeypatch
):
    import app.backend.services.analysis.engine as engine

    called: list[int] = []
    monkeypatch.setattr(engine, "on_analysis_completed", lambda tid: called.append(tid))

    _failing_llm(monkeypatch, ["内容"])  # 命中所有条目
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B"}
    )
    tid = _make_task(client, admin_headers, {"mode": "per_item"}, [sid])

    run = _run(client, admin_headers, tid)
    assert run["status"] == "failed"
    assert "全部" in (run["error"] or "")

    st = _db_state(tid)
    assert st["result_count"] == 0
    assert all(v is False for v in st["analyzed"].values())
    assert st["watermark"] is None
    # 关键回归：无异常但结果为空的运行 MUST NOT 触发推送（空正文邮件的直接原因）
    assert called == []


def test_empty_llm_output_is_not_counted_as_success(
    client, admin_headers, sync_worker, monkeypatch
):
    """纵深防御：即便 client 直接返回空串（绕过其内部校验），引擎也判为失败。

    这正是本次故障的形态——空内容被当成成功结果落库并推送出一封空正文邮件。
    """
    import app.backend.services.analysis.engine as engine

    called: list[int] = []
    monkeypatch.setattr(engine, "on_analysis_completed", lambda tid: called.append(tid))

    class _Empty:
        def __init__(self, *a, **kw):
            pass

        def chat(self, system, user):
            return ""

    monkeypatch.setattr(engine, "LLMClient", _Empty)
    sid = _make_folder_source(client, admin_headers, {"a.txt": "内容A"})
    tid = _make_task(client, admin_headers, {"mode": "per_item"}, [sid])

    run = _run(client, admin_headers, tid)
    assert run["status"] == "failed"

    st = _db_state(tid)
    assert st["result_count"] == 0
    assert all(v is False for v in st["analyzed"].values())
    assert st["watermark"] is None
    assert called == []


# ---------- aggregate 模式失败 ----------


def test_aggregate_failure_marks_run_failed_without_touching_watermark(
    client, admin_headers, sync_worker, monkeypatch
):
    import app.backend.services.analysis.engine as engine

    called: list[int] = []
    monkeypatch.setattr(engine, "on_analysis_completed", lambda tid: called.append(tid))

    _failing_llm(monkeypatch, ["内容"])
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B"}
    )
    tid = _make_task(client, admin_headers, {"mode": "aggregate"}, [sid])

    run = _run(client, admin_headers, tid, mode="full")
    assert run["status"] == "failed"

    st = _db_state(tid)
    assert st["result_count"] == 0
    assert all(v is False for v in st["analyzed"].values())
    assert st["watermark"] is None
    assert called == []


def test_aggregate_success_still_marks_all_items_analyzed(
    client, admin_headers, sync_worker, monkeypatch
):
    """回归：aggregate 正常路径不受影响。"""
    _failing_llm(monkeypatch, [])
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B"}
    )
    tid = _make_task(client, admin_headers, {"mode": "aggregate"}, [sid])

    run = _run(client, admin_headers, tid, mode="full")
    assert run["status"] == "succeeded"

    st = _db_state(tid)
    assert st["result_count"] == 1
    assert all(v is True for v in st["analyzed"].values())
    assert st["watermark"] == max(st["item_ids"])


# ---------- custom 模式失败 ----------


def test_custom_mode_partial_failure_skips_only_that_item(
    client, admin_headers, sync_worker, monkeypatch
):
    sid = _make_folder_source(
        client, admin_headers, {"a.txt": "内容A", "b.txt": "内容B"}
    )
    st0 = _db_state(None, sid)
    selected = sorted(st0["item_ids"])
    failed_id = selected[0]
    _failing_llm(monkeypatch, [_marker_for(st0, failed_id)])

    tid = _make_task(
        client,
        admin_headers,
        {"mode": "custom", "custom_item_ids": selected},
        [sid],
    )
    run = _run(client, admin_headers, tid, mode="custom")
    assert run["status"] == "succeeded"
    assert "失败 1 条" in run["summary"]

    st = _db_state(tid, sid)
    assert st["result_item_ids"] == [i for i in selected if i != failed_id]
    assert st["analyzed"][failed_id] is False
    # 自定义模式不推进水位线
    assert st["watermark"] is None
