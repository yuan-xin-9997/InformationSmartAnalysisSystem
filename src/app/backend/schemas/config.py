"""System-config schemas."""
from __future__ import annotations

from pydantic import BaseModel


class RuntimeInfo(BaseModel):
    started_at: str | None
    pid: int
    version: str
    host: str
    port: int
    db_path: str
    log_dir: str
    data_dir: str
    python_version: str


class ConfigResponse(BaseModel):
    config: dict
    runtime: RuntimeInfo
