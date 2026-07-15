"""Config loader unit tests."""
from __future__ import annotations


def test_config_loaded_from_env():
    from app.backend.core.config import settings

    # conftest set ISAS_DB_PATH to a temp test.sqlite3
    assert settings.database_path.name == "test.sqlite3"
    assert settings.auth_secret_key == "test-secret"


def test_env_override(monkeypatch):
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_SERVER_PORT", "9999")
    monkeypatch.setenv("ISAS_LLM_MODEL", "test-model")
    s = Settings()
    assert s.server_port == 9999
    assert s.llm_model == "test-model"
