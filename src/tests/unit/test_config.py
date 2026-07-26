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


def test_scheduler_settings():
    from app.backend.core.config import settings

    assert settings.scheduler_enabled is True
    assert settings.scheduler_misfire_grace_seconds == 300
    assert settings.scheduler_max_instances == 1
    assert settings.scheduler_coalesce is True


def test_email_settings_defaults():
    from app.backend.core.config import settings

    # app.json 的 email 段默认值（留空待部署方填写）
    assert settings.email_smtp_host == ""
    assert settings.email_smtp_port == 25
    assert settings.email_use_tls is False
    assert settings.email_use_ssl is False
    assert settings.email_username == ""
    assert settings.email_password == ""
    assert settings.email_from_email == ""
    assert settings.email_from_name == "信息智能分析系统"


def test_email_env_override(monkeypatch):
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_EMAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ISAS_EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("ISAS_EMAIL_USE_TLS", "true")
    monkeypatch.setenv("ISAS_EMAIL_USE_SSL", "false")
    monkeypatch.setenv("ISAS_EMAIL_USERNAME", "user@example.com")
    monkeypatch.setenv("ISAS_EMAIL_PASSWORD", "pw123")
    monkeypatch.setenv("ISAS_EMAIL_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("ISAS_EMAIL_FROM_NAME", "推送机器人")
    s = Settings()
    assert s.email_smtp_host == "smtp.example.com"
    assert s.email_smtp_port == 587
    assert s.email_use_tls is True
    assert s.email_use_ssl is False
    assert s.email_username == "user@example.com"
    assert s.email_password == "pw123"
    assert s.email_from_email == "noreply@example.com"
    assert s.email_from_name == "推送机器人"
