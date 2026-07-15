"""Analysis schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase


class AnalysisTaskOut(ORMBase):
    id: int
    name: str
    description: str
    config: dict
    created_at: BeijingDatetime
    updated_at: BeijingDatetime


class AnalysisTaskCreate(ORMBase):
    name: str
    description: str = ""
    config: dict = {}
    source_ids: list[int] = []


class AnalysisTaskUpdate(ORMBase):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    source_ids: list[int] | None = None


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
