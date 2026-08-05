"""OCR service client unit tests (CLAUDE.md 架构要求 5)."""
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
    from app.backend.services.clients.ocr_client import OCRClient

    return OCRClient(base_url="http://mock-ocr", api_key="key-ocr")


# ---------- construction / config ----------


def test_ocr_client_rejects_missing_config(monkeypatch):
    from app.backend.services.clients import ocr_client as mod

    monkeypatch.setattr(mod.settings, "ocr_base_url", "")
    monkeypatch.setattr(mod.settings, "ocr_api_key", "")
    with pytest.raises(mod.OCRError, match="未配置"):
        mod.OCRClient()


def test_ocr_client_uses_settings_defaults(monkeypatch):
    """When constructed without args, client pulls defaults from settings."""
    from app.backend.services.clients.ocr_client import OCRClient

    monkeypatch.setattr(
        "app.backend.services.clients.ocr_client.settings",
        type(
            "S",
            (),
            {
                "ocr_base_url": "http://nas-ocr",
                "ocr_api_key": "k",
                "ocr_timeout_seconds": 200,
                "ocr_mode": "markdown",
                "ocr_language": "zh-Hans",
            },
        )(),
    )
    c = OCRClient()
    assert c.base_url == "http://nas-ocr"
    assert c.api_key == "k"
    assert c.timeout == 200
    assert c.mode == "markdown"
    assert c.language == "zh-Hans"


# ---------- ocr() ----------


@pytest.fixture
def captured(monkeypatch):
    """Capture ``httpx.post`` calls; ``captured['resp']`` controls the response."""
    state: dict = {
        "posts": [],
        "resp": _FakeResp(payload={"text": "page text", "pages": 1}),
    }

    def _post(url, files=None, data=None, headers=None, timeout=None):
        state["posts"].append(
            {"url": url, "files": files, "data": data, "headers": headers, "timeout": timeout}
        )
        return state["resp"]

    monkeypatch.setattr(httpx, "post", _post)
    return state


def test_ocr_returns_text_and_sends_multipart(captured):
    client = _make_client()
    img = b"\x89PNG\r\n\x1a\nfake-png"
    out = client.ocr(img, filename="p1.png")
    assert out == "page text"

    call = captured["posts"][-1]
    assert call["url"] == "http://mock-ocr/v1/ocr"
    assert call["headers"]["Authorization"] == "Bearer key-ocr"
    # multipart file tuple (filename, bytes, mime)
    fname, fbytes, fmime = call["files"]["file"]
    assert fname == "p1.png"
    assert fbytes == img
    assert fmime == "image/png"
    assert call["data"] == {"mode": "text", "language": "auto"}


def test_ocr_mode_and_language_override(captured):
    client = _make_client()
    client.ocr(b"x", mode="markdown", language="zh-Hans")
    assert captured["posts"][-1]["data"] == {"mode": "markdown", "language": "zh-Hans"}


def test_ocr_4xx_raises_ocr_error(captured):
    from app.backend.services.clients.ocr_client import OCRError

    captured["resp"] = _FakeResp(status_code=401, text="unauthorized")
    with pytest.raises(OCRError, match="OCR 返回 401"):
        _make_client().ocr(b"x")


def test_ocr_timeout_raises_ocr_error(monkeypatch):
    from app.backend.services.clients.ocr_client import OCRError

    def _post(url, files=None, data=None, headers=None, timeout=None):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "post", _post)
    with pytest.raises(OCRError, match="超时"):
        _make_client().ocr(b"x")


def test_ocr_http_error_raises_ocr_error(monkeypatch):
    from app.backend.services.clients.ocr_client import OCRError

    def _post(url, files=None, data=None, headers=None, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", _post)
    with pytest.raises(OCRError, match="调用 OCR 服务失败"):
        _make_client().ocr(b"x")


def test_ocr_malformed_response_raises(captured):
    from app.backend.services.clients.ocr_client import OCRError

    captured["resp"] = _FakeResp(payload={"unexpected": True})
    with pytest.raises(OCRError, match="缺少 text 字段"):
        _make_client().ocr(b"x")


def test_ocr_non_json_response_raises(captured):
    from app.backend.services.clients.ocr_client import OCRError

    captured["resp"] = _FakeResp(payload=None, text="<html>502</html>")
    with pytest.raises(OCRError, match="非 JSON"):
        _make_client().ocr(b"x")


# ---------- health() ----------


def test_ocr_health_ok(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, headers=None, timeout=None: _FakeResp(payload={"status": "ok"}),
    )
    assert _make_client().health() is True


def test_ocr_health_fail_on_error(monkeypatch):
    def _get(url, headers=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", _get)
    assert _make_client().health() is False
