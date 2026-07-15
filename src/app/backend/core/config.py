"""Application configuration loader.

Reads ``config/app.json`` (located relative to the project ``src`` root) and
applies environment-variable overrides for host/sensitive values. Nothing
environment-specific (IP, port, credentials, absolute paths) is hard-coded in
source code (CLAUDE.md 规范1).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Runtime root = the ``src`` directory (parents[3] from core/config.py:
# core -> backend -> app -> src).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]


def _resolve_path(value: str) -> Path:
    """Resolve a possibly-relative path against the project root."""
    p = Path(value)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def _env(name: str, default: Any = None) -> Any:
    return os.environ.get(name, default)


class Settings:
    """Strongly-typed view over ``app.json`` with env-var overrides."""

    def __init__(self) -> None:
        config_path = Path(_env("ISAS_CONFIG", PROJECT_ROOT / "config" / "app.json"))
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        with config_path.open(encoding="utf-8") as fh:
            raw: dict[str, Any] = json.load(fh)
        self._raw = raw

        server = raw.get("server", {})
        self.server_host: str = _env("ISAS_SERVER_HOST", server.get("host", "0.0.0.0"))
        self.server_port: int = int(_env("ISAS_SERVER_PORT", server.get("port", 8000)))

        db = raw.get("database", {})
        self.database_path: Path = _resolve_path(
            _env("ISAS_DB_PATH", db.get("path", "data/app.sqlite3"))
        )

        auth = raw.get("auth", {})
        self.auth_secret_key: str = _env(
            "ISAS_AUTH_SECRET_KEY", auth.get("secret_key", "change-me")
        )
        self.token_expire_minutes: int = int(
            _env("ISAS_TOKEN_EXPIRE_MINUTES", auth.get("token_expire_minutes", 720))
        )
        self.password_file: Path = _resolve_path(
            _env("ISAS_PASSWORD_FILE", auth.get("password_file", "data/password.txt"))
        )

        wf = raw.get("web_fetch", {})
        self.web_fetch_base_url: str = _env(
            "ISAS_WEB_FETCH_BASE_URL", wf.get("base_url", "")
        )
        self.web_fetch_api_key: str = _env("ISAS_WEB_FETCH_API_KEY", wf.get("api_key", ""))
        self.web_fetch_timeout: int = int(
            _env("ISAS_WEB_FETCH_TIMEOUT", wf.get("timeout_seconds", 30))
        )

        llm = raw.get("llm", {})
        self.llm_base_url: str = _env("ISAS_LLM_BASE_URL", llm.get("base_url", ""))
        self.llm_api_key: str = _env("ISAS_LLM_API_KEY", llm.get("api_key", ""))
        self.llm_model: str = _env("ISAS_LLM_MODEL", llm.get("model", "gpt-4o-mini"))
        self.llm_temperature: float = float(
            _env("ISAS_LLM_TEMPERATURE", llm.get("temperature", 0.3))
        )
        self.llm_max_tokens: int = int(_env("ISAS_LLM_MAX_TOKENS", llm.get("max_tokens", 2000)))
        self.llm_timeout: int = int(_env("ISAS_LLM_TIMEOUT", llm.get("timeout_seconds", 60)))

        fr = raw.get("freshrss", {})
        self.freshrss_default_base_url: str = fr.get("default_base_url", "")
        self.freshrss_default_user: str = fr.get("default_user", "")
        self.freshrss_default_api_token: str = fr.get("default_api_token", "")

        lg = raw.get("logging", {})
        self.log_level: str = _env("ISAS_LOG_LEVEL", lg.get("level", "INFO"))
        self.log_dir: Path = _resolve_path(_env("ISAS_LOG_DIR", lg.get("dir", "logs")))
        self.log_retention_days: int = int(lg.get("retention_days", 30))

        self.data_dir: Path = _resolve_path(_env("ISAS_DATA_DIR", raw.get("data_dir", "data")))
        self.timezone_display: str = raw.get("timezone_display", "Asia/Shanghai")

        wk = raw.get("worker", {})
        self.worker_max_workers: int = int(
            _env("ISAS_WORKER_MAX_WORKERS", wk.get("max_workers", 4))
        )

    @property
    def raw(self) -> dict[str, Any]:
        """The raw parsed ``app.json`` dict (for the system-config page)."""
        return self._raw


settings = Settings()
