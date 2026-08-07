"""Push service core tests: incremental watermark, batching, failure, no_new, on_run hook."""
from __future__ import annotations

from datetime import datetime, timezone

from app.backend.core.database import SessionLocal
from app.backend.models.analysis import AnalysisResult, AnalysisTask
from app.backend.models.push import PushRule, PushRun, get_smtp_config_row
from app.backend.models.task import TaskRun
from app.backend.services.push import service as push_service


def _setup_smtp(db):
    cfg = get_smtp_config_row(db)
    cfg.host = "smtp.x.com"
    cfg.from_email = "f@x.com"
    db.commit()


def _make_task(db, name: str, specs: list[tuple[str, str]]) -> tuple[int, list[int]]:
    """Create a task + a succeeded run + results. specs: [(result_type, content), ...]."""
    task = AnalysisTask(name=name, description="", config={})
    db.add(task)
    db.commit()
    db.refresh(task)
    run = TaskRun(kind="analysis", ref_id=task.id, ref_name=task.name, status="succeeded")
    db.add(run)
    db.commit()
    db.refresh(run)
    for rt, content in specs:
        db.add(
            AnalysisResult(
                task_run_id=run.id, task_id=task.id, result_type=rt, content=content
            )
        )
    db.commit()
    results = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.task_id == task.id)
        .order_by(AnalysisResult.id.asc())
        .all()
    )
    return task.id, [r.id for r in results]


class _FakeChannel:
    def __init__(self, fail_on: int | None = None):
        self.fail_on = fail_on  # 1-based call index that raises
        self.n = 0
        self.calls: list[str] = []
        self.sent_htmls: list[str] = []
        self.sent_inlines: list[list] = []

    def send(self, cfg, recipients, subject, html, text, attachments=None, inline_images=None):
        self.n += 1
        if self.fail_on and self.n == self.fail_on:
            raise RuntimeError("smtp boom")
        self.calls.append(subject)
        self.sent_htmls.append(html)
        self.sent_inlines.append(inline_images or [])


def _patch_channel(monkeypatch, channel):
    monkeypatch.setattr(push_service, "get_channel", lambda name: channel)


def test_incremental_push_only_new(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", "c1"), ("per_item", "c2"), ("per_item", "c3")])
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="manual",
            last_pushed_result_id=rids[0],  # 已推到第1条 -> 只推第2、3条
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    assert len(fake.calls) == 1
    with SessionLocal() as db:
        rule = db.get(PushRule, rid)
        assert rule.last_pushed_result_id == rids[2]
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "succeeded"
        assert run.event_count == 2


def test_first_push_sends_all_matching(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", "c1"), ("per_item", "c2")])
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="manual",
        )  # 水位线为空
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    assert len(fake.calls) == 1
    with SessionLocal() as db:
        rule = db.get(PushRule, rid)
        assert rule.last_pushed_result_id == rids[1]
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "succeeded"
        assert run.event_count == 2


def test_filter_by_task_and_event_type(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid_a, _ = _make_task(db, "A", [("per_item", "a1"), ("aggregate", "a2")])
        tid_b, _ = _make_task(db, "B", [("per_item", "b1")])
        rule = PushRule(
            name="r",
            task_id=tid_a,  # 只选任务A
            event_types=["per_item"],  # 只选 per_item
            recipients=["a@x.com"],
            trigger_mode="manual",
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    # 只推送 A 的 per_item（1条），A 的 aggregate 与 B 的 per_item 不推
    with SessionLocal() as db:
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "succeeded"
        assert run.event_count == 1


def test_batching_sends_multiple_emails(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", f"c{i}") for i in range(5)])
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="manual",
            max_events_per_email=2,  # 5条 -> 3批(2,2,1)
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    assert len(fake.calls) == 3
    with SessionLocal() as db:
        rule = db.get(PushRule, rid)
        assert rule.last_pushed_result_id == rids[-1]
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "succeeded"
        assert run.event_count == 5


def test_failure_does_not_advance_watermark(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", f"c{i}") for i in range(5)])
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="manual",
            max_events_per_email=2,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel(fail_on=2)  # 第2批发送失败
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    with SessionLocal() as db:
        rule = db.get(PushRule, rid)
        # 第1批(rids[0],rids[1])成功推进水位线到 rids[1]；第2批失败不推进
        assert rule.last_pushed_result_id == rids[1]
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "failed"
        assert run.event_count == 2  # 失败前已发1批


def test_no_new_events_records_no_new(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", "c1")])
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="manual",
            last_pushed_result_id=rids[0],  # 已推完，无新事件
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    assert fake.calls == []
    with SessionLocal() as db:
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "no_new"
        assert run.event_count == 0


def test_on_analysis_completed_triggers_matching_rules(client, sync_worker, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", "c1")])
        tid_other, _ = _make_task(db, "OTHER", [("per_item", "o1")])  # 另一个任务
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="on_run",
        )
        other = PushRule(
            name="other",
            task_id=tid_other,  # 归属另一个任务，不匹配 tid
            event_types=["per_item"],
            recipients=["b@x.com"],
            trigger_mode="on_run",
        )
        db.add_all([rule, other])
        db.commit()
        db.refresh(rule)
        rid = rule.id
        other_rid = other.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.on_analysis_completed(tid)
    with SessionLocal() as db:
        run = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run.status == "succeeded"
        assert run.event_count == 1
        # 归属另一个任务的 on_run 规则不被触发
        assert db.query(PushRun).filter(PushRun.rule_id == other_rid).count() == 0


def test_on_analysis_completed_disabled_rule_not_triggered(client, sync_worker, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, _ = _make_task(db, "T", [("per_item", "c1")])
        rule = PushRule(
            name="r",
            task_id=tid,
            event_types=["per_item"],
            recipients=["a@x.com"],
            trigger_mode="on_run",
            enabled=False,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.on_analysis_completed(tid)
    assert fake.calls == []
    with SessionLocal() as db:
        assert db.query(PushRun).filter(PushRun.rule_id == rid).count() == 0


def test_to_push_event_fills_per_item_fields(client):
    from app.backend.services.push.service import _to_push_event
    from app.backend.models.info_source import InfoItem, InfoSource

    with SessionLocal() as db:
        src = InfoSource(name="源", type="local_folder", config={})
        db.add(src)
        db.flush()
        item = InfoItem(
            source_id=src.id, external_id="/path/report.pdf", title="report.pdf",
            author="张三", author_affiliation="高盛",
            article_published_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            page_count=12, content="c",
        )
        db.add(item)
        db.flush()
        task = AnalysisTask(name="T", config={})
        db.add(task)
        db.flush()
        run = TaskRun(kind="analysis", ref_id=task.id, ref_name="T", status="succeeded")
        db.add(run)
        db.flush()
        r = AnalysisResult(
            task_run_id=run.id, task_id=task.id, source_id=src.id,
            info_item_id=item.id, result_type="per_item", content="分析内容",
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        e = _to_push_event(db, r)
    assert e.task_name == "T"
    assert e.source_name == "源"
    assert e.item_title == "report.pdf"
    assert e.file_path == "/path/report.pdf"
    assert e.author == "张三"
    assert e.author_affiliation == "高盛"
    assert e.page_count == 12
    assert e.article_published_at is not None


def test_to_push_event_aggregate_has_no_item_fields(client):
    from app.backend.services.push.service import _to_push_event

    with SessionLocal() as db:
        task = AnalysisTask(name="T", config={})
        db.add(task)
        db.flush()
        run = TaskRun(kind="analysis", ref_id=task.id, ref_name="T", status="succeeded")
        db.add(run)
        db.flush()
        r = AnalysisResult(
            task_run_id=run.id, task_id=task.id, source_id=None,
            info_item_id=None, result_type="aggregate", content="汇总",
        )
        db.add(r)
        db.commit()
        db.refresh(r)
        e = _to_push_event(db, r)
    assert e.result_type == "aggregate"
    assert e.item_title is None
    assert e.file_path is None
    assert e.author is None


# ---- push-email-preview-inline-figures: 邮件内容留存 ----

import pathlib
import tempfile
from app.backend.core.config import settings
from app.backend.models.info_source import InfoItem, InfoItemFigure, InfoSource


def _make_per_item_with_figure(db, task_id, run_id, src, fig_bytes=b"\x89PNG\r\n\x1a\n fake"):
    """Create an InfoItem + figure file under figures_dir + per_item AnalysisResult."""
    item = InfoItem(
        source_id=src.id, external_id="http://x/a.html", title="doc.html", content="c",
    )
    db.add(item)
    db.flush()
    fd = pathlib.Path(settings.figures_dir)
    fd.mkdir(parents=True, exist_ok=True)
    fp = fd / f"fig_{item.id}_0.png"
    fp.write_bytes(fig_bytes)
    db.add(InfoItemFigure(item_id=item.id, figure_index=0, storage_path=str(fp), mime="image/png"))
    r = AnalysisResult(
        task_run_id=run_id, task_id=task_id, source_id=src.id,
        info_item_id=item.id, result_type="per_item", content="分析内容",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_succeeded_push_persists_email_html_with_data_urls(client, monkeypatch):
    """成功推送：PushRun 留存 subject/email_html（图表 data:）/attachment_summary。"""
    with SessionLocal() as db:
        _setup_smtp(db)
        task = AnalysisTask(name="T", config={})
        db.add(task)
        db.flush()
        run = TaskRun(kind="analysis", ref_id=task.id, ref_name="T", status="succeeded")
        db.add(run)
        db.flush()
        src = InfoSource(name="网站", type="website", config={"url": "http://x"})
        db.add(src)
        db.flush()
        r = _make_per_item_with_figure(db, task.id, run.id, src)
        rule = PushRule(
            name="r", task_id=task.id, event_types=["per_item"],
            recipients=["a@x.com"], trigger_mode="manual",
        )
        db.add(rule)
        db.commit()
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    with SessionLocal() as db:
        run_row = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run_row.status == "succeeded"
        assert run_row.subject is not None
        assert "1条新事件" in run_row.subject
        # 预览 HTML：图表以 data: 内嵌（浏览器可渲染），不再有 cid:
        assert "data:image/png;base64," in run_row.email_html
        assert "cid:" not in (run_row.email_html or "")
        assert "分析内容" in run_row.email_html
        # 附件清单：图表（来自内联图）
        assert run_row.attachment_summary is not None
        kinds = {a["kind"] for a in run_row.attachment_summary}
        assert "figure" in kinds


def test_no_new_does_not_persist_email_content(client, monkeypatch):
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, rids = _make_task(db, "T", [("per_item", "c1")])
        rule = PushRule(
            name="r", task_id=tid, event_types=["per_item"], recipients=["a@x.com"],
            trigger_mode="manual", last_pushed_result_id=rids[0],
        )
        db.add(rule)
        db.commit()
        rid = rule.id
    push_service.run_push(rid, "manual")
    with SessionLocal() as db:
        run_row = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run_row.status == "no_new"
        assert run_row.subject is None
        assert run_row.email_html is None
        assert run_row.attachment_summary is None


def test_multi_batch_merges_preview_html(client, monkeypatch):
    """多批：1 条 PushRun，email_html 含多封分隔。"""
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, _ = _make_task(db, "T", [("per_item", f"c{i}") for i in range(5)])
        rule = PushRule(
            name="r", task_id=tid, event_types=["per_item"], recipients=["a@x.com"],
            trigger_mode="manual", max_events_per_email=2,  # 5 -> 3 批
        )
        db.add(rule)
        db.commit()
        rid = rule.id
    fake = _FakeChannel()
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    with SessionLocal() as db:
        run_row = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run_row.status == "succeeded"
        assert "第 1 封 / 共 3 封" in run_row.email_html
        assert "第 2 封 / 共 3 封" in run_row.email_html
        assert "第 3 封 / 共 3 封" in run_row.email_html


def test_failure_after_first_batch_keeps_partial_preview(client, monkeypatch):
    """第 2 批失败：状态 failed，email_html 仍留存第 1 批内容。"""
    with SessionLocal() as db:
        _setup_smtp(db)
        tid, _ = _make_task(db, "T", [("per_item", f"c{i}") for i in range(5)])
        rule = PushRule(
            name="r", task_id=tid, event_types=["per_item"], recipients=["a@x.com"],
            trigger_mode="manual", max_events_per_email=2,
        )
        db.add(rule)
        db.commit()
        rid = rule.id
    fake = _FakeChannel(fail_on=2)
    _patch_channel(monkeypatch, fake)
    push_service.run_push(rid, "manual")
    with SessionLocal() as db:
        run_row = db.query(PushRun).filter(PushRun.rule_id == rid).one()
        assert run_row.status == "failed"
        # 第 1 批成功：邮件正文留存；无多封分隔
        assert run_row.email_html is not None
        assert "c0" in run_row.email_html
        assert "第 1 封" not in run_row.email_html  # 单批无分隔
