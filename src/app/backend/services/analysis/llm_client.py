"""OpenAI-compatible LLM client (configurable base_url/api_key/model)."""
from __future__ import annotations

from typing import Any

import httpx

from ...core.config import settings
from ...core.logging import get_logger

_logger = get_logger("llm")


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Calls any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.temperature = (
            temperature if temperature is not None else settings.llm_temperature
        )
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self.timeout = timeout or settings.llm_timeout
        if not self.base_url or not self.api_key:
            raise LLMError("LLM base_url 或 api_key 未配置")

    def chat(self, system: str, user: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"调用 LLM 失败: {exc}") from exc
        if r.status_code >= 400:
            raise LLMError(f"LLM 返回 {r.status_code}: {r.text[:300]}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"LLM 响应格式异常: {r.text[:300]}") from exc
