"""Analysis schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase
from .info_source import SourceFileOut


# ---- Per-task schedule config (1:1 with AnalysisTask) ----

class ScheduleConfigBase(ORMBase):
    """Upsert payload for a task's 1:1 scheduled-analysis config."""

    enabled: bool = True
    mode: str  # full | incremental
    trigger_type: str  # cron | interval
    cron_expr: str | None = None
    interval_seconds: int | None = None


class ScheduleConfigOut(ScheduleConfigBase):
    id: int
    last_run_at: BeijingDatetime | None = None
    last_run_status: str | None = None
    next_run_at: BeijingDatetime | None = None
    created_at: BeijingDatetime
    updated_at: BeijingDatetime


# ---- Per-task push config (1:1 with AnalysisTask) ----

class PushConfigBase(ORMBase):
    """Upsert payload for a task's 1:1 push config."""

    enabled: bool = True
    event_types: list[str] = []
    recipients: list[str] = []
    trigger_mode: str  # on_run | scheduled | manual
    cron_expr: str | None = None
    interval_seconds: int | None = None
    max_events_per_email: int = 50


class PushConfigOut(PushConfigBase):
    id: int
    last_pushed_result_id: int | None = None
    created_at: BeijingDatetime
    updated_at: BeijingDatetime


class AnalysisTaskOut(ORMBase):
    id: int
    name: str
    description: str
    config: dict
    created_at: BeijingDatetime
    updated_at: BeijingDatetime
    schedule: ScheduleConfigOut | None = None
    push: PushConfigOut | None = None


class AnalysisTaskCreate(ORMBase):
    name: str
    description: str = ""
    config: dict = {}
    source_ids: list[int] = []
    schedule: ScheduleConfigBase | None = None
    push: PushConfigBase | None = None


class AnalysisTaskUpdate(ORMBase):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    source_ids: list[int] | None = None
    # null = delete the sub-config; object = upsert; absent = leave untouched
    # (distinguish via ``model_dump(exclude_unset=True)`` in the API layer).
    schedule: ScheduleConfigBase | None = None
    push: PushConfigBase | None = None


class TaskSourceOut(ORMBase):
    source_id: int
    source_name: str
    source_type: str
    source_status: str
    item_count: int
    last_analyzed_item_id: int | None
    last_analyzed_at: BeijingDatetime | None


class AnalysisTaskDetailOut(AnalysisTaskOut):
    sources: list[TaskSourceOut] = []


class RunAnalysisRequest(ORMBase):
    mode: str = "incremental"  # full | incremental


class AnalysisResultOut(ORMBase):
    id: int
    task_run_id: int
    task_id: int
    source_id: int | None
    source_name: str | None
    info_item_id: int | None
    result_type: str
    content: str
    created_at: BeijingDatetime
    # per_item 结果携带来源文件信息；aggregate 结果为 None。
    source_file: SourceFileOut | None = None
