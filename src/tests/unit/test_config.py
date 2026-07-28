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


def test_figures_dir_defaults_to_data_dir_figures():
    """figures_dir defaults to data_dir/figures (empty app.json value)."""
    from app.backend.core.config import settings

    assert settings.figures_dir == settings.data_dir / "figures"


def test_max_figures_per_item_default():
    """max_figures_per_item defaults to 20."""
    from app.backend.core.config import settings

    assert settings.max_figures_per_item == 20


def test_figures_dir_env_override(monkeypatch):
    """ISAS_FIGURES_DIR overrides the default data_dir/figures."""
    from app.backend.core.config import PROJECT_ROOT, Settings

    monkeypatch.setenv("ISAS_FIGURES_DIR", "custom/figs")
    s = Settings()
    assert s.figures_dir == PROJECT_ROOT / "custom" / "figs"


def test_figures_dir_env_override_absolute(monkeypatch, tmp_path):
    """ISAS_FIGURES_DIR with an absolute path is used as-is."""
    from app.backend.core.config import Settings

    abs_dir = tmp_path / "abs-figs"
    monkeypatch.setenv("ISAS_FIGURES_DIR", str(abs_dir))
    s = Settings()
    assert s.figures_dir == abs_dir


def test_max_figures_per_item_env_override(monkeypatch):
    """ISAS_MAX_FIGURES_PER_ITEM overrides the default 20."""
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_MAX_FIGURES_PER_ITEM", "50")
    s = Settings()
    assert s.max_figures_per_item == 50


def test_figures_dir_config_file_override(monkeypatch, tmp_path):
    """app.json figures_dir (non-empty) is used when env var is absent."""
    import json

    from app.backend.core.config import PROJECT_ROOT, Settings

    cfg = tmp_path / "app.json"
    cfg.write_text(
        json.dumps({"figures_dir": "from_config/figs"}), encoding="utf-8"
    )
    monkeypatch.setenv("ISAS_CONFIG", str(cfg))
    monkeypatch.delenv("ISAS_FIGURES_DIR", raising=False)
    s = Settings()
    assert s.figures_dir == PROJECT_ROOT / "from_config" / "figs"


def test_max_figures_per_item_config_file_override(monkeypatch, tmp_path):
    """app.json max_figures_per_item is used when env var is absent."""
    import json

    from app.backend.core.config import Settings

    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"max_figures_per_item": 99}), encoding="utf-8")
    monkeypatch.setenv("ISAS_CONFIG", str(cfg))
    monkeypatch.delenv("ISAS_MAX_FIGURES_PER_ITEM", raising=False)
    s = Settings()
    assert s.max_figures_per_item == 99
