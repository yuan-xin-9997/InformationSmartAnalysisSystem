"""LLM client unit tests (validation + clear errors)."""
from __future__ import annotations

import base64

import httpx
import pytest


def test_llm_client_rejects_placeholder_key():
    from app.backend.services.analysis.llm_client import LLMClient, LLMError

    with pytest.raises(LLMError, match="占位符"):
        LLMClient(base_url="https://api.example.com/v1", api_key="sk-请替换为真实Key")


def test_llm_client_rejects_non_ascii_key():
    from app.backend.services.analysis.llm_client import LLMClient, LLMError

    with pytest.raises(LLMError, match="非 ASCII"):
        LLMClient(base_url="https://api.example.com/v1", api_key="sk-真实key含中文")


def test_llm_client_rejects_missing_config(monkeypatch):
    from app.backend.services.analysis import llm_client as mod
    from app.backend.services.analysis.llm_client import LLMError

    monkeypatch.setattr(mod.settings, "llm_base_url", "")
    monkeypatch.setattr(mod.settings, "llm_api_key", "")
    import pytest

    with pytest.raises(LLMError, match="未配置"):
        mod.LLMClient()


def test_llm_client_accepts_real_ascii_key():
    """A real ascii key + base_url should construct without raising."""
    from app.backend.services.analysis.llm_client import LLMClient

    client = LLMClient(
        base_url="https://api.deepseek.com/v1",
        api_key="sk-real-ascii-key-12345",
        model="deepseek-chat",
    )
    assert client.model == "deepseek-chat"


# ---------- chat (text) & chat_with_images (vision) ----------


class _FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


@pytest.fixture
def captured(monkeypatch):
    """Capture ``httpx.post`` calls; ``captured['resp']`` controls the response."""
    state: dict = {
        "posts": [],
        "resp": _FakeResp(payload={"choices": [{"message": {"content": "ok"}}]}),
    }

    def _post(url, json=None, headers=None, timeout=None):
        state["posts"].append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        return state["resp"]

    monkeypatch.setattr(httpx, "post", _post)
    return state


def _make_client():
    from app.backend.services.analysis.llm_client import LLMClient

    return LLMClient(base_url="http://mock-llm", api_key="sk-mock", model="gpt-4o-mini")


def test_chat_sends_text_messages_and_returns_content(captured):
    client = _make_client()
    out = client.chat("sys", "hello")

    assert out == "ok"
    body = captured["posts"][-1]["json"]
    assert body["model"] == "gpt-4o-mini"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]


def test_chat_4xx_raises_llm_error(captured):
    from app.backend.services.analysis.llm_client import LLMError

    captured["resp"] = _FakeResp(status_code=400, text="bad request")
    client = _make_client()
    with pytest.raises(LLMError, match="LLM 返回 400"):
        client.chat("sys", "u")


def test_chat_with_images_builds_vision_payload(captured):
    client = _make_client()
    img = b"\x89PNG\r\n\x1a\nfake-png-bytes"
    client.chat_with_images("sys", "extract text", [img])

    body = captured["posts"][-1]["json"]
    assert body["model"] == "gpt-4o-mini"
    messages = body["messages"]
    assert messages[0] == {"role": "system", "content": "sys"}
    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    # text part first, then one image part
    assert user_content[0] == {"type": "text", "text": "extract text"}
    img_part = user_content[1]
    assert img_part["type"] == "image_url"
    url = img_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    b64 = url[len("data:image/png;base64,") :]
    assert base64.b64decode(b64) == img


def test_chat_with_images_multiple_images(captured):
    client = _make_client()
    client.chat_with_images("s", "u", [b"a", b"bb", b"ccc"])
    user_content = captured["posts"][-1]["json"]["messages"][1]["content"]
    # 1 text + 3 images
    assert len(user_content) == 4
    assert sum(1 for p in user_content if p["type"] == "image_url") == 3


def test_chat_with_images_custom_mime(captured):
    client = _make_client()
    client.chat_with_images("s", "u", [b"x"], mime="image/jpeg")
    url = captured["posts"][-1]["json"]["messages"][1]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")


def test_chat_with_images_returns_content(captured):
    captured["resp"] = _FakeResp(
        payload={"choices": [{"message": {"content": "extracted page text"}}]}
    )
    client = _make_client()
    assert client.chat_with_images("s", "u", [b"x"]) == "extracted page text"


def test_chat_with_images_4xx_raises_llm_error(captured):
    from app.backend.services.analysis.llm_client import LLMError

    captured["resp"] = _FakeResp(status_code=404, text="model not found")
    client = _make_client()
    with pytest.raises(LLMError, match="LLM 返回 404"):
        client.chat_with_images("s", "u", [b"x"])


def test_chat_with_images_malformed_response_raises(captured):
    from app.backend.services.analysis.llm_client import LLMError

    captured["resp"] = _FakeResp(payload={"unexpected": True})
    client = _make_client()
    with pytest.raises(LLMError, match="响应格式异常"):
        client.chat_with_images("s", "u", [b"x"])


def test_chat_with_images_retries_once_on_timeout(monkeypatch):
    """A first timeout triggers one retry; success on second call."""
    client = _make_client()
    calls = {"n": 0}

    def _post(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.TimeoutException("slow")
        return _FakeResp(payload={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", _post)
    assert client.chat_with_images("s", "u", [b"x"]) == "ok"
    assert calls["n"] == 2
