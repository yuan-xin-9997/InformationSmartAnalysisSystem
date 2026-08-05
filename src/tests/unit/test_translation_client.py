"""Translation service client unit tests (CLAUDE.md 架构要求 4)."""
from __future__ import annotations

import httpx
import pytest


class _FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def _make_client():
    from app.backend.services.clients.translation_client import TranslationClient

    return TranslationClient(base_url="http://mock-tr", api_key="key-tr")


# ---------- construction / config ----------


def test_translate_client_rejects_missing_config(monkeypatch):
    from app.backend.services.clients import translation_client as mod

    monkeypatch.setattr(mod.settings, "translate_base_url", "")
    monkeypatch.setattr(mod.settings, "translate_api_key", "")
    with pytest.raises(mod.TranslationError, match="未配置"):
        mod.TranslationClient()


def test_translate_client_defaults_from_settings(monkeypatch):
    from app.backend.services.clients.translation_client import TranslationClient

    monkeypatch.setattr(
        "app.backend.services.clients.translation_client.settings",
        type(
            "S",
            (),
            {
                "translate_base_url": "http://nas-tr",
                "translate_api_key": "k",
                "translate_timeout_seconds": 90,
                "translate_default_target": "en",
                "translate_default_mode": "fast",
            },
        )(),
    )
    c = TranslationClient()
    assert c.base_url == "http://nas-tr"
    assert c.default_target == "en"
    assert c.default_mode == "fast"
    assert c.timeout == 90


# ---------- translate() ----------


@pytest.fixture
def captured(monkeypatch):
    state: dict = {
        "posts": [],
        "resp": _FakeResp(
            payload={"translation": "你好", "model": "translategemma:4b", "chunks": 1}
        ),
    }

    def _post(url, json=None, headers=None, timeout=None):
        state["posts"].append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return state["resp"]

    monkeypatch.setattr(httpx, "post", _post)
    return state


def test_translate_returns_translation_and_sends_json(captured):
    client = _make_client()
    out = client.translate("Hello", target="zh-Hans", mode="fast")
    assert out == "你好"

    call = captured["posts"][-1]
    assert call["url"] == "http://mock-tr/v1/translate"
    assert call["headers"]["Authorization"] == "Bearer key-tr"
    assert call["json"] == {
        "text": "Hello",
        "source": "auto",
        "target": "zh-Hans",
        "mode": "fast",
        "format": "text",
    }


def test_translate_uses_default_target_and_mode(captured):
    """Omitted target/mode fall back to client defaults."""
    client = _make_client()
    client.translate("Hi")
    body = captured["posts"][-1]["json"]
    assert body["target"] == "zh-Hans"  # settings default
    assert body["mode"] == "quality"  # settings default


def test_translate_4xx_raises(monkeypatch):
    from app.backend.services.clients.translation_client import TranslationError

    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, json=None, headers=None, timeout=None: _FakeResp(
            status_code=401, text="unauthorized"
        ),
    )
    with pytest.raises(TranslationError, match="翻译服务返回 401"):
        _make_client().translate("x")


def test_translate_timeout_raises(monkeypatch):
    from app.backend.services.clients.translation_client import TranslationError

    def _post(url, json=None, headers=None, timeout=None):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "post", _post)
    with pytest.raises(TranslationError, match="超时"):
        _make_client().translate("x")


def test_translate_http_error_raises(monkeypatch):
    from app.backend.services.clients.translation_client import TranslationError

    def _post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", _post)
    with pytest.raises(TranslationError, match="调用翻译服务失败"):
        _make_client().translate("x")


def test_translate_malformed_response_raises(captured):
    from app.backend.services.clients.translation_client import TranslationError

    captured["resp"] = _FakeResp(payload={"unexpected": True})
    with pytest.raises(TranslationError, match="缺少 translation 字段"):
        _make_client().translate("x")


def test_translate_health_ok(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, headers=None, timeout=None: _FakeResp(payload={"status": "ok"}),
    )
    assert _make_client().health() is True
