"""Push SMTP config API tests: GET/PUT (masking), test email, permission."""
from __future__ import annotations

from app.backend.core.database import SessionLocal
from app.backend.models.push import get_smtp_config_row


def _tester_headers(client) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"username": "tester", "password": "tester123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_get_smtp_returns_masked_password(client, admin_headers):
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        cfg.host = "smtp.x.com"
        cfg.password = "secret123"
        db.commit()
    r = client.get("/api/push/smtp", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["host"] == "smtp.x.com"
    assert body["password"] != "secret123"  # 脱敏
    assert "******" in body["password"]


def test_put_smtp_saves_and_keeps_password_when_empty(client, admin_headers):
    r = client.put(
        "/api/push/smtp",
        json={"host": "smtp.x.com", "port": 587, "password": "pw1", "from_email": "n@x.com"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    # password 为空时保留旧密码（避免前端回传脱敏值覆盖真实密码）
    r2 = client.put(
        "/api/push/smtp",
        json={"host": "smtp.x.com", "port": 587, "password": "", "from_email": "n@x.com"},
        headers=admin_headers,
    )
    assert r2.status_code == 200
    with SessionLocal() as db:
        cfg = get_smtp_config_row(db)
        assert cfg.password == "pw1"
        assert cfg.host == "smtp.x.com"


def test_test_smtp_ok(client, admin_headers, monkeypatch):
    client.put(
        "/api/push/smtp",
        json={"host": "smtp.x.com", "port": 587, "from_email": "n@x.com", "password": "pw"},
        headers=admin_headers,
    )
    from app.backend.services.push.channels import email_channel

    sent = {}

    def _fake_send(self, cfg, recipients, subject, html, text):
        sent["recipients"] = list(recipients)
        sent["subject"] = subject

    monkeypatch.setattr(email_channel.EmailChannel, "send", _fake_send)
    r = client.post("/api/push/smtp/test", json={"to_email": "to@x.com"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert sent["recipients"] == ["to@x.com"]


def test_test_smtp_not_configured(client, admin_headers, monkeypatch):
    monkeypatch.setattr("app.backend.core.config.settings.email_smtp_host", "")
    client.put("/api/push/smtp", json={"host": "", "from_email": ""}, headers=admin_headers)
    r = client.post("/api/push/smtp/test", json={"to_email": "to@x.com"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_smtp_endpoints_require_permission(client):
    h = _tester_headers(client)
    assert client.get("/api/push/smtp", headers=h).status_code == 403
    assert client.put("/api/push/smtp", json={}, headers=h).status_code == 403
    assert client.post("/api/push/smtp/test", json={"to_email": "x@x.com"}, headers=h).status_code == 403
