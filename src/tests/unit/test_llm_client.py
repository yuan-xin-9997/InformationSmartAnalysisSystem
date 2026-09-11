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
    """Capture ``httpx.post`` calls; ``captured['resp']`` controls the response.

    Set ``captured['resps']`` to a list to return a different response per call
    (the last entry repeats once the list is exhausted).
    """
    state: dict = {
        "posts": [],
        "resp": _FakeResp(payload={"choices": [{"message": {"content": "ok"}}]}),
    }

    def _post(url, json=None, headers=None, timeout=None):
        state["posts"].append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        resps = state.get("resps")
        if resps:
            idx = min(len(state["posts"]) - 1, len(resps) - 1)
            return resps[idx]
        return state["resp"]

    monkeypatch.setattr(httpx, "post", _post)
    return state


def _make_client(**kwargs):
    from app.backend.services.analysis.llm_client import LLMClient

    opts = {
        "base_url": "http://mock-llm",
        "api_key": "sk-mock",
        "model": "gpt-4o-mini",
    }
    opts.update(kwargs)
    return LLMClient(**opts)


def _choice(content=None, finish_reason=None, **message_extra):
    """Build a ``choices[0]`` payload for a chat-completion response."""
    message: dict = dict(message_extra)
    if content is not None:
        message["content"] = content
    return {"choices": [{"finish_reason": finish_reason, "message": message}]}


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


# ---------- 输出有效性校验：空内容 / 截断 / max_tokens 下限 ----------
#
# 这些用例守护的线上故障：推理模型因 max_tokens 过小，思考阶段耗尽预算，
# 返回空 content + finish_reason="length"；旧实现照原样返回空串，引擎据此
# 把条目判为成功并推送，最终发出一封空正文邮件。


def test_chat_empty_content_raises(captured):
    """空 content 不得被当成有效结果返回。"""
    from app.backend.services.analysis.llm_client import LLMError

    captured["resp"] = _FakeResp(payload=_choice(content="", finish_reason="stop"))
    client = _make_client()
    with pytest.raises(LLMError, match="空内容"):
        client.chat("sys", "u")


def test_chat_whitespace_only_content_raises(captured):
    from app.backend.services.analysis.llm_client import LLMError

    captured["resp"] = _FakeResp(payload=_choice(content="  \n\t ", finish_reason="stop"))
    client = _make_client()
    with pytest.raises(LLMError, match="空内容"):
        client.chat("sys", "u")


def test_chat_missing_content_key_raises(captured):
    """响应里没有 content 键（旧实现返回 None）同样判为失败。"""
    from app.backend.services.analysis.llm_client import LLMError

    captured["resp"] = _FakeResp(payload=_choice(finish_reason="stop"))
    client = _make_client()
    with pytest.raises(LLMError, match="空内容"):
        client.chat("sys", "u")


def test_chat_falls_back_to_reasoning_content(captured):
    """部分推理模型把内容放在 reasoning_content，content 为空时应回退。"""
    captured["resp"] = _FakeResp(
        payload=_choice(content="", finish_reason="stop", reasoning_content="思考结果")
    )
    client = _make_client()
    assert client.chat("sys", "u") == "思考结果"


def test_chat_retries_truncated_with_doubled_max_tokens(captured):
    """finish_reason=length -> 以翻倍 max_tokens 重试一次并返回结果。"""
    captured["resps"] = [
        _FakeResp(payload=_choice(content="半截", finish_reason="length")),
        _FakeResp(payload=_choice(content="完整结果", finish_reason="stop")),
    ]
    client = _make_client(max_tokens=16000)
    assert client.chat("sys", "u") == "完整结果"

    posts = captured["posts"]
    assert len(posts) == 2
    assert posts[0]["json"]["max_tokens"] == 16000
    assert posts[1]["json"]["max_tokens"] == 32000


def test_chat_truncated_twice_raises_truncated_error(captured):
    from app.backend.services.analysis.llm_client import LLMTruncatedError

    captured["resp"] = _FakeResp(payload=_choice(content="还是半截", finish_reason="length"))
    client = _make_client(max_tokens=8000)
    with pytest.raises(LLMTruncatedError, match="截断"):
        client.chat("sys", "u")
    assert len(captured["posts"]) == 2  # 只重试一次，不无限循环


def test_truncation_retry_is_capped(captured):
    """翻倍重试不得超过 MAX_TOKENS_RETRY_CAP。"""
    from app.backend.services.analysis.llm_client import MAX_TOKENS_RETRY_CAP

    captured["resps"] = [
        _FakeResp(payload=_choice(content="", finish_reason="length")),
        _FakeResp(payload=_choice(content="ok", finish_reason="stop")),
    ]
    client = _make_client(max_tokens=20000)
    assert client.chat("sys", "u") == "ok"
    assert captured["posts"][1]["json"]["max_tokens"] == MAX_TOKENS_RETRY_CAP == 32000


def test_max_tokens_below_floor_is_raised(captured):
    """部署侧陈旧配置（2000）应被抬到安全下限，避免再次发出空正文邮件。"""
    from app.backend.services.analysis.llm_client import MIN_MAX_TOKENS

    client = _make_client(max_tokens=2000)
    client.chat("sys", "u")
    assert captured["posts"][-1]["json"]["max_tokens"] == MIN_MAX_TOKENS == 4096


def test_max_tokens_above_floor_is_untouched(captured):
    client = _make_client(max_tokens=16000)
    client.chat("sys", "u")
    assert captured["posts"][-1]["json"]["max_tokens"] == 16000
