"""Analysis engine: orchestrates a task run (full or incremental).

Runs in the background worker. Opens its own DB session. ``llm_client`` can be
injected for testing; otherwise built from settings (+ per-task model override).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func

from ...core.database import SessionLocal
from ...core.logging import get_logger
from ...core.timeutil import utcnow, iso_beijing
from ...models.analysis import AnalysisResult, AnalysisTask, TaskSource
from ...models.info_source import InfoItem, InfoSource
from ...models.scheduled_job import ScheduledJob
from ...models.task import TaskLog, TaskRun
from ..push.service import on_analysis_completed
from ..info_source.refresh import refresh, as_dict
from . import prompts as P
from .llm_client import LLMClient, LLMError

_logger = get_logger("analysis")


def _log(db, run_id: int, level: str, message: str) -> None:
    db.add(TaskLog(run_id=run_id, level=level, message=message))
    db.commit()


def _make_llm(task_config: dict) -> LLMClient:
    model = (task_config or {}).get("model") or None
    return LLMClient(model=model)


def _call_llm(
    llm: LLMClient, system: str, user: str, db, run_id: int, label: str
) -> str | None:
    """调用 LLM；失败时记 WARNING 并返回 ``None``（不中断整批分析）。

    ``LLMClient`` 已保证返回值非空且未被截断（截断会以翻倍预算重试一次），
    这里再校验一次空内容是**纵深防御**：只要结果为空，就绝不能落库、绝不能
    被判定为成功——否则会推送出一封空正文邮件。注入的 mock/第三方 client
    同样受此约束。

    单条失败不应让整批 50 条白跑：调用方按 ``None`` 跳过该条目——不落库、
    不置 ``analyzed``、不推进水位线——并在运行摘要中计入失败数。
    """
    try:
        content = llm.chat(system, user)
    except LLMError as exc:
        _log(db, run_id, "WARNING", f"[{label}] 分析失败，跳过该条目: {exc}")
        return None
    if not (content or "").strip():
        _log(db, run_id, "WARNING", f"[{label}] 分析失败，跳过该条目: LLM 返回空内容")
        return None
    return content


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

        # 仅当本次运行真正产出有效结果时才触发推送（见文件末尾的推送钩子）。
        analysis_ok = False
        failed_count = 0

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
            source_ids = [ts.source_id for ts in task_sources]
            db.commit()  # release the read transaction before sync writes via another session
            refresh_results = []
            refresh_started = utcnow()
            if cfg.get("refresh_before_run", True):
                max_age = int(cfg.get("refresh_max_age_seconds", 900))
                if max_age < 0:
                    raise ValueError("数据新鲜度有效期不能为负数")
                for source_id in source_ids:
                    try:
                        result = refresh(source_id, max_age)
                        detail = as_dict(result)
                    except Exception:
                        _logger.error("更新信息源失败: %s", source_id)
                        source = db.get(InfoSource, source_id)
                        detail = {"source_id": source_id, "source_name": source.name if source else "(已删除)",
                                  "status": "failed", "added_count": 0, "updated_count": 0,
                                  "error": "更新数据失败，请查看服务日志", "started_at": iso_beijing(utcnow()),
                                  "finished_at": iso_beijing(utcnow())}
                    refresh_results.append(detail)
                    _log(db, run_id, "WARNING" if detail["status"] == "failed" else "INFO",
                         f"更新数据 [{detail['source_name']}]: {detail['status']}, 新增 {detail['added_count']}, 更新 {detail['updated_count']}"
                         + (f", 原因: {detail.get('reason') or detail.get('error')}" if detail.get('reason') or detail.get('error') else ""))
            else:
                _log(db, run_id, "INFO", "已关闭分析前更新数据")
            refresh_finished = utcnow()
            run.refresh_detail = {"started_at": iso_beijing(refresh_started), "finished_at": iso_beijing(refresh_finished),
                                  "sources": refresh_results, "analysis_started_at": iso_beijing(utcnow())}
            db.commit()
            db.expire_all()
            failed_refreshes = sum(r["status"] == "failed" for r in refresh_results)
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
                    content = _call_llm(
                        llm, system, user, db, run_id, f"条目#{it.id}"
                    )
                    if content is None:
                        failed_count += 1
                        continue
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
                strategy = str(cfg.get("selection_strategy") or "sequential").strip()
                if strategy not in ("sequential", "newest_unanalyzed"):
                    _log(db, run_id, "WARNING", f"未知条目选择策略 {strategy!r}，回退 sequential")
                    strategy = "sequential"
                for ts in task_sources:
                    source = ts.source
                    if source is None:
                        continue
                    q = db.query(InfoItem).filter(InfoItem.source_id == ts.source_id)
                    if strategy == "newest_unanalyzed":
                        # 未分析中按时间倒序取最新 N 篇，不依赖水位线筛选
                        time_key = func.coalesce(
                            InfoItem.published_at,
                            InfoItem.article_published_at,
                            InfoItem.fetched_at,
                        )
                        q = q.filter(InfoItem.analyzed.is_(False))
                        items = q.order_by(time_key.desc(), InfoItem.id.desc()).limit(max_per).all()
                    else:
                        if mode == "incremental" and ts.last_analyzed_item_id:
                            q = q.filter(InfoItem.id > ts.last_analyzed_item_id)
                        items = q.order_by(InfoItem.id.asc()).limit(max_per).all()

                    if not items:
                        _log(db, run_id, "INFO", f"源 [{source.name}] 无新内容，跳过")
                        continue
                    _log(db, run_id, "INFO", f"源 [{source.name}] 待分析 {len(items)} 条")

                    if analysis_mode == "aggregate":
                        system, user = P.render_aggregate(system_prompt, user_template, items)
                        content = _call_llm(
                            llm, system, user, db, run_id, f"源[{source.name}] 聚合"
                        )
                        if content is None:
                            # 整批聚合失败：不落库、不置 analyzed、不推进水位线
                            failed_count += len(items)
                        else:
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
                            ts.last_analyzed_item_id = max(it.id for it in items)
                            ts.last_analyzed_at = utcnow()
                    else:
                        # 水位线只推进到本批**成功**条目的最大 id：失败条目（尤其是
                        # 集中在批次尾部时）下次增量会自动重跑。失败若夹在中间，
                        # 该条目会被水位线越过，需用「全量」或「自定义」模式补跑——
                        # 故 _call_llm 的 WARNING 会写明条目 id 供人工排查。
                        ok_ids: list[int] = []
                        for it in items:
                            system, user = P.render_per_item(system_prompt, user_template, it)
                            content = _call_llm(
                                llm, system, user, db, run_id, f"条目#{it.id}"
                            )
                            if content is None:
                                failed_count += 1
                                continue
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
                            ok_ids.append(it.id)
                            total_results += 1
                        if ok_ids:
                            ts.last_analyzed_item_id = max(ok_ids)
                            ts.last_analyzed_at = utcnow()

                    total_items += len(items)

            run.finished_at = utcnow()
            run.refresh_detail = {**(run.refresh_detail or {}), "analysis_finished_at": iso_beijing(run.finished_at)}
            run.summary = f"分析完成: 处理 {total_items} 条信息, 生成 {total_results} 条结果"
            if failed_refreshes:
                run.summary += f"; 部分更新失败 ({failed_refreshes}/{len(refresh_results)})" if failed_refreshes < len(refresh_results) else "; 所有来源更新失败"
            if failed_refreshes and total_items == 0:
                run.status = "failed"
                run.error = "信息源更新失败，且没有可分析的增量数据"
            if failed_count:
                run.summary += f", 失败 {failed_count} 条 (详见任务日志 WARNING)"
            # 全部条目都失败时不得记为成功——否则会触发推送发出一封空正文邮件。
            if failed_count and total_results == 0:
                run.status = "failed"
                run.error = f"全部 {failed_count} 条分析失败，未产生任何结果"
            elif run.status != "failed":
                run.status = "succeeded"
                analysis_ok = True
            _log(db, run_id, "INFO", run.summary)
            if run.scheduled_job_id:
                sj = db.get(ScheduledJob, run.scheduled_job_id)
                if sj:
                    sj.last_run_status = run.status
            db.commit()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("分析任务失败: %s", task.name)
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            _log(db, run_id, "ERROR", f"分析失败: {exc}")
            if run.scheduled_job_id:
                sj = db.get(ScheduledJob, run.scheduled_job_id)
                if sj:
                    sj.last_run_status = "failed"
            db.commit()
        else:
            # 推送钩子：**仅当运行状态为 succeeded** 时才触发 on_run 推送。
            # 不能只判断「未抛异常」——全部条目分析失败时状态为 failed 但不抛异常，
            # 那样仍会推送出一封空正文邮件（本次故障的直接原因）。异常隔离：
            # on_analysis_completed 自身吞掉错误，不影响已成功的分析结果。
            if analysis_ok:
                on_analysis_completed(task_id)
