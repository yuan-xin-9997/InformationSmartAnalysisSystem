"""LLM client unit tests (validation + clear errors)."""
from __future__ import annotations

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
