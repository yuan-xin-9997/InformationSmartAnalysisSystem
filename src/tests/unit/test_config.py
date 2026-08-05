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


# ---------- extraction (vision-LLM fallback) settings ----------


def test_extraction_settings_defaults(monkeypatch):
    """extraction 节默认值（env 缺省时）：兜底启用、模型留空复用 llm.model、阈值与页数上限。"""
    from app.backend.core.config import Settings

    for var in (
        "ISAS_EXTRACTION_VISION_FALLBACK",
        "ISAS_EXTRACTION_VISION_MODEL",
        "ISAS_EXTRACTION_MAX_OCR_PAGES",
        "ISAS_EXTRACTION_MIN_TEXT_LENGTH",
        "ISAS_EXTRACTION_READABLE_RATIO",
        "ISAS_EXTRACTION_RENDER_DPI",
    ):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.extraction_vision_fallback is True
    assert s.extraction_vision_model == ""
    assert s.extraction_max_ocr_pages == 10
    assert s.extraction_min_text_length == 50
    assert s.extraction_readable_ratio == 0.6
    assert s.extraction_render_dpi == 150


def test_extraction_env_override(monkeypatch):
    """ISAS_EXTRACTION_* 环境变量覆盖默认值。"""
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_EXTRACTION_VISION_FALLBACK", "false")
    monkeypatch.setenv("ISAS_EXTRACTION_VISION_MODEL", "gpt-4o")
    monkeypatch.setenv("ISAS_EXTRACTION_MAX_OCR_PAGES", "5")
    monkeypatch.setenv("ISAS_EXTRACTION_MIN_TEXT_LENGTH", "100")
    monkeypatch.setenv("ISAS_EXTRACTION_READABLE_RATIO", "0.8")
    monkeypatch.setenv("ISAS_EXTRACTION_RENDER_DPI", "200")
    s = Settings()
    assert s.extraction_vision_fallback is False
    assert s.extraction_vision_model == "gpt-4o"
    assert s.extraction_max_ocr_pages == 5
    assert s.extraction_min_text_length == 100
    assert s.extraction_readable_ratio == 0.8
    assert s.extraction_render_dpi == 200


def test_extraction_config_file_override(monkeypatch, tmp_path):
    """app.json extraction 节在 env 缺省时生效。"""
    import json

    from app.backend.core.config import Settings

    cfg = tmp_path / "app.json"
    cfg.write_text(
        json.dumps(
            {"extraction": {"vision_fallback": False, "max_ocr_pages": 3, "render_dpi": 120}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ISAS_CONFIG", str(cfg))
    for var in (
        "ISAS_EXTRACTION_VISION_FALLBACK",
        "ISAS_EXTRACTION_MAX_OCR_PAGES",
        "ISAS_EXTRACTION_RENDER_DPI",
    ):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.extraction_vision_fallback is False
    assert s.extraction_max_ocr_pages == 3
    assert s.extraction_render_dpi == 120


# ---------- OCR / 翻译服务配置 ----------


def test_ocr_settings_defaults(monkeypatch, tmp_path):
    """ocr 节代码默认值（app.json 无 ocr 块时）：超时 120s、mode text、language auto。"""
    import json

    from app.backend.core.config import Settings

    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("ISAS_CONFIG", str(cfg))
    for var in (
        "ISAS_OCR_BASE_URL",
        "ISAS_OCR_API_KEY",
        "ISAS_OCR_TIMEOUT",
        "ISAS_OCR_MODE",
        "ISAS_OCR_LANGUAGE",
    ):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.ocr_base_url == ""
    assert s.ocr_api_key == ""
    assert s.ocr_timeout_seconds == 120
    assert s.ocr_mode == "text"
    assert s.ocr_language == "auto"


def test_ocr_env_override(monkeypatch):
    """ISAS_OCR_* 环境变量覆盖默认值。"""
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_OCR_BASE_URL", "https://ocr.example.com")
    monkeypatch.setenv("ISAS_OCR_API_KEY", "key-ocr")
    monkeypatch.setenv("ISAS_OCR_TIMEOUT", "180")
    monkeypatch.setenv("ISAS_OCR_MODE", "markdown")
    monkeypatch.setenv("ISAS_OCR_LANGUAGE", "zh-Hans")
    s = Settings()
    assert s.ocr_base_url == "https://ocr.example.com"
    assert s.ocr_api_key == "key-ocr"
    assert s.ocr_timeout_seconds == 180
    assert s.ocr_mode == "markdown"
    assert s.ocr_language == "zh-Hans"


def test_translate_settings_defaults(monkeypatch, tmp_path):
    """translate 节代码默认值（app.json 无 translate 块时）：超时 60s、target zh-Hans、mode quality。"""
    import json

    from app.backend.core.config import Settings

    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("ISAS_CONFIG", str(cfg))
    for var in (
        "ISAS_TRANSLATE_BASE_URL",
        "ISAS_TRANSLATE_API_KEY",
        "ISAS_TRANSLATE_TIMEOUT",
        "ISAS_TRANSLATE_DEFAULT_TARGET",
        "ISAS_TRANSLATE_DEFAULT_MODE",
    ):
        monkeypatch.delenv(var, raising=False)
    s = Settings()
    assert s.translate_base_url == ""
    assert s.translate_api_key == ""
    assert s.translate_timeout_seconds == 60
    assert s.translate_default_target == "zh-Hans"
    assert s.translate_default_mode == "quality"


def test_translate_env_override(monkeypatch):
    """ISAS_TRANSLATE_* 环境变量覆盖默认值。"""
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_TRANSLATE_BASE_URL", "https://translate.example.com")
    monkeypatch.setenv("ISAS_TRANSLATE_API_KEY", "key-tr")
    monkeypatch.setenv("ISAS_TRANSLATE_TIMEOUT", "90")
    monkeypatch.setenv("ISAS_TRANSLATE_DEFAULT_TARGET", "en")
    monkeypatch.setenv("ISAS_TRANSLATE_DEFAULT_MODE", "fast")
    s = Settings()
    assert s.translate_base_url == "https://translate.example.com"
    assert s.translate_api_key == "key-tr"
    assert s.translate_timeout_seconds == 90
    assert s.translate_default_target == "en"
    assert s.translate_default_mode == "fast"


def test_extraction_vision_model_still_readable_but_deprecated(monkeypatch):
    """extraction_vision_model 已废弃但仍可读取（向后兼容），不影响新逻辑。"""
    from app.backend.core.config import Settings

    monkeypatch.setenv("ISAS_EXTRACTION_VISION_MODEL", "gpt-4o")
    s = Settings()
    # 仍可读取（向后兼容旧 app.json / env）
    assert s.extraction_vision_model == "gpt-4o"
    # 但新兜底逻辑不再使用它：OCR 配置独立存在
    assert hasattr(s, "ocr_base_url")
