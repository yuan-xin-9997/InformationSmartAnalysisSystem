"""Background worker: a process-wide thread pool for long-running jobs
(info-source sync, analysis task runs).

Each job runs in its own thread with its own DB session. The API creates a
``TaskRun`` row (pending) in the request session, then submits the job by id.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from ..core.config import settings
from ..core.logging import get_logger

_logger = get_logger("worker")

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=settings.worker_max_workers,
            thread_name_prefix="isas-worker",
        )
    return _executor


def submit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
    return get_executor().submit(_safe, fn, *args, **kwargs)


def _safe(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001  (worker must never crash silently)
        _logger.exception("后台任务执行异常")


def shutdown() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
