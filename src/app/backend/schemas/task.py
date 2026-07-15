"""Task-run / task-log schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase


class TaskRunOut(ORMBase):
    id: int
    kind: str
    ref_id: int | None
    ref_name: str
    mode: str | None
    status: str
    started_at: BeijingDatetime | None
    finished_at: BeijingDatetime | None
    summary: str | None
    error: str | None
    created_at: BeijingDatetime


class TaskLogOut(ORMBase):
    id: int
    run_id: int | None
    level: str
    message: str
    created_at: BeijingDatetime


class TaskRunDetailOut(TaskRunOut):
    logs: list[TaskLogOut] = []
