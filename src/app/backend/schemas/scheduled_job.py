"""Scheduled-job schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase


class ScheduledJobOut(ORMBase):
    id: int
    task_id: int
    name: str
    mode: str
    trigger_type: str
    cron_expr: str | None
    interval_seconds: int | None
    enabled: bool
    last_run_at: BeijingDatetime | None
    last_run_status: str | None
    next_run_at: BeijingDatetime | None
    created_at: BeijingDatetime
    updated_at: BeijingDatetime


class ScheduledJobCreate(ORMBase):
    task_id: int
    name: str
    mode: str  # full | incremental
    trigger_type: str  # cron | interval
    cron_expr: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True


class ScheduledJobUpdate(ORMBase):
    name: str | None = None
    mode: str | None = None
    trigger_type: str | None = None
    cron_expr: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None
