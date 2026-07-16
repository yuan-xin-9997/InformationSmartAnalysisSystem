"""Analysis engine: orchestrates a task run (full or incremental).

Runs in the background worker. Opens its own DB session. ``llm_client`` can be
injected for testing; otherwise built from settings (+ per-task model override).
"""
from __future__ import annotations

from typing import Any

from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...core.timeutil import utcnow
from ...models.analysis import AnalysisResult, AnalysisTask, TaskSource
from ...models.info_source import InfoItem
from ...models.task import TaskLog, TaskRun
from . import prompts as P
from .llm_client import LLMClient, LLMError

_logger = get_logger("analysis")


def _log(db, run_id: int, level: str, message: str) -> None:
    db.add(TaskLog(run_id=run_id, level=level, message=message))
    db.commit()


def _make_llm(task_config: dict) -> LLMClient:
    model = (task_config or {}).get("model") or None
    return LLMClient(model=model)


def run_analysis(
    run_id: int,
    task_id: int,
    mode: str = "incremental",
    llm_client: LLMClient | None = None,
) -> None:
    with SessionLocal() as db:
        run = db.get(TaskRun, run_id)
        if run is None:
            return
        task = db.get(AnalysisTask, task_id)
        if task is None:
            run.status = "failed"
            run.error = "分析任务不存在"
            run.finished_at = utcnow()
            db.commit()
            return

        run.status = "running"
        run.started_at = utcnow()
        db.commit()
        _log(db, run_id, "INFO", f"开始分析任务: {task.name} (模式: {mode})")

        try:
            cfg: dict[str, Any] = task.config or {}
            analysis_mode = cfg.get("mode") or "per_item"  # per_item | aggregate
            max_per = int(cfg.get("max_items_per_source") or 50)
            system_prompt = cfg.get("system_prompt") or ""
            user_template = cfg.get("user_prompt_template") or ""
            llm = llm_client or _make_llm(cfg)

            task_sources = (
                db.query(TaskSource).filter(TaskSource.task_id == task_id).all()
            )
            total_items = 0
            total_results = 0

            # 自定义模式：分析用户在任务 config.custom_item_ids 中指定的条目（不推进水位线）。
            if analysis_mode == "custom" or mode == "custom":
                custom_ids = list(cfg.get("custom_item_ids") or [])
                bound_ids = [ts.source_id for ts in task_sources]
                items = []
                if custom_ids and bound_ids:
                    items = (
                        db.query(InfoItem)
                        .filter(
                            InfoItem.id.in_(custom_ids),
                            InfoItem.source_id.in_(bound_ids),
                        )
                        .order_by(InfoItem.id.asc())
                        .all()
                    )
                if not items:
                    _log(db, run_id, "WARNING", "自定义模式未选中任何条目（或选中条目不属于已绑定信息源）")
                else:
                    _log(db, run_id, "INFO", f"自定义模式：分析选中的 {len(items)} 条")
                for it in items:
                    system, user = P.render_per_item(system_prompt, user_template, it)
                    content = llm.chat(system, user)
                    db.add(
                        AnalysisResult(
                            task_run_id=run_id,
                            task_id=task_id,
                            source_id=it.source_id,
                            info_item_id=it.id,
                            result_type="per_item",
                            content=content,
                        )
                    )
                    it.analyzed = True
                    total_results += 1
                total_items = len(items)
            else:
                for ts in task_sources:
                    source = ts.source
                    if source is None:
                        continue
                    q = db.query(InfoItem).filter(InfoItem.source_id == ts.source_id)
                    if mode == "incremental" and ts.last_analyzed_item_id:
                        q = q.filter(InfoItem.id > ts.last_analyzed_item_id)
                    items = q.order_by(InfoItem.id.asc()).limit(max_per).all()

                    if not items:
                        _log(db, run_id, "INFO", f"源 [{source.name}] 无新内容，跳过")
                        continue
                    _log(db, run_id, "INFO", f"源 [{source.name}] 待分析 {len(items)} 条")

                    if analysis_mode == "aggregate":
                        system, user = P.render_aggregate(system_prompt, user_template, items)
                        content = llm.chat(system, user)
                        db.add(
                            AnalysisResult(
                                task_run_id=run_id,
                                task_id=task_id,
                                source_id=ts.source_id,
                                info_item_id=None,
                                result_type="aggregate",
                                content=content,
                            )
                        )
                        for it in items:
                            it.analyzed = True
                        total_results += 1
                    else:
                        for it in items:
                            system, user = P.render_per_item(system_prompt, user_template, it)
                            content = llm.chat(system, user)
                            db.add(
                                AnalysisResult(
                                    task_run_id=run_id,
                                    task_id=task_id,
                                    source_id=ts.source_id,
                                    info_item_id=it.id,
                                    result_type="per_item",
                                    content=content,
                                )
                            )
                            it.analyzed = True
                            total_results += 1

                    ts.last_analyzed_item_id = items[-1].id
                    ts.last_analyzed_at = utcnow()
                    total_items += len(items)

            run.status = "succeeded"
            run.finished_at = utcnow()
            run.summary = f"分析完成: 处理 {total_items} 条信息, 生成 {total_results} 条结果"
            _log(db, run_id, "INFO", run.summary)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("分析任务失败: %s", task.name)
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            _log(db, run_id, "ERROR", f"分析失败: {exc}")
            db.commit()
