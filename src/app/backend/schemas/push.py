"""Push schemas: SMTP config, push rules, push runs (history)."""
from __future__ import annotations

from pydantic import BaseModel

from .common import BeijingDatetime, ORMBase


class SmtpConfigOut(BaseModel):
    host: str
    port: int
    use_tls: bool
    use_ssl: bool
    username: str
    from_email: str
    from_name: str
    password: str  # 脱敏后的展示值


class SmtpConfigIn(BaseModel):
    host: str = ""
    port: int = 25
    use_tls: bool = False
    use_ssl: bool = False
    username: str = ""
    password: str = ""  # 空表示保留旧密码（避免前端回传脱敏值覆盖）
    from_email: str = ""
    from_name: str = "信息智能分析系统"


class TestEmailRequest(BaseModel):
    to_email: str


# ---- Push rules ----

_TRIGGER_MODES = ("on_run", "scheduled", "manual")


class PushRuleCreate(BaseModel):
    name: str
    channel: str = "email"
    task_ids: list[int] = []
    event_types: list[str] = []
    recipients: list[str] = []
    trigger_mode: str  # on_run | scheduled | manual
    cron_expr: str | None = None
    interval_seconds: int | None = None
    enabled: bool = True
    max_events_per_email: int = 50


class PushRuleUpdate(BaseModel):
    name: str | None = None
    channel: str | None = None
    task_ids: list[int] | None = None
    event_types: list[str] | None = None
    recipients: list[str] | None = None
    trigger_mode: str | None = None
    cron_expr: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None
    max_events_per_email: int | None = None


class PushRuleOut(ORMBase):
    id: int
    name: str
    channel: str
    task_ids: list[int]
    event_types: list[str]
    recipients: list[str]
    trigger_mode: str
    cron_expr: str | None
    interval_seconds: int | None
    enabled: bool
    last_pushed_result_id: int | None
    max_events_per_email: int
    created_at: BeijingDatetime
    updated_at: BeijingDatetime


class PushRunOut(ORMBase):
    id: int
    rule_id: int
    trigger_mode: str
    recipients: list[str]
    event_count: int
    status: str
    error: str | None
    started_at: BeijingDatetime | None
    finished_at: BeijingDatetime | None
    created_at: BeijingDatetime

