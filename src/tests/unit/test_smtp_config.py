"""SMTP config resolver tests: page > app.json > error."""
from __future__ import annotations

import pytest

from app.backend.core.config import settings
from app.backend.core.database import SessionLocal
from app.backend.models.push import get_smtp_config_row
from app.backend.services.push.smtp_config import SmtpConfigError, resolve_smtp_config


def test_page_config_takes_priority(client, monkeypatch):
    monkeypatch.setattr(settings, "email_smtp_host", "apphost.example.com")
    monkeypatch.setattr(settings, "email_from_email", "app@x.com")
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        cfg.host = "pagehost.example.com"
        cfg.port = 587
        cfg.from_email = "page@x.com"
        cfg.password = "pw"
        db.commit()
        resolved = resolve_smtp_config(db)
    assert resolved.host == "pagehost.example.com"
    assert resolved.from_email == "page@x.com"
    assert resolved.source == "page"


def test_fallback_to_app_json_when_page_empty(client, monkeypatch):
    monkeypatch.setattr(settings, "email_smtp_host", "apphost.example.com")
    monkeypatch.setattr(settings, "email_smtp_port", 25)
    monkeypatch.setattr(settings, "email_from_email", "app@x.com")
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        cfg.host = ""  # 页面未配置
        db.commit()
        resolved = resolve_smtp_config(db)
    assert resolved.host == "apphost.example.com"
    assert resolved.from_email == "app@x.com"
    assert resolved.source == "app.json"


def test_missing_both_raises(client, monkeypatch):
    monkeypatch.setattr(settings, "email_smtp_host", "")
    monkeypatch.setattr(settings, "email_from_email", "")
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        cfg.host = ""
        db.commit()
        with pytest.raises(SmtpConfigError):
            resolve_smtp_config(db)
