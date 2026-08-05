"""Client for the NAS local translation service (CLAUDE.md 架构要求 4).

Service contract (from its OpenAPI at ``/docs``):
- Base URL + ``Authorization: Bearer <api_key>`` header.
- ``POST /v1/translate``  JSON body: ``text`` (required), ``source`` (default
  ``auto``), ``target`` (default ``zh-Hans``), ``mode`` (quality|fast, default
  ``quality``), ``format`` (text|markdown, default ``text``).
- Response JSON: ``{"translation": str, "model": str, "source": str,
  "target": str, "mode": str, "chunks": int}``.

This client is currently scaffolding only -- no business flow calls it yet
(per change ``local-ocr-translation-services``). Future integrations (e.g.
pre-analysis translation of foreign-language items) will use it.
"""
from __future__ import annotations

import httpx

from ...core.config import settings
from ...core.logging import get_logger

_logger = get_logger("translate")


class TranslationError(RuntimeError):
    pass


class TranslationClient:
    """Calls the local translation service ``POST /v1/translate``."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        default_target: str | None = None,
        default_mode: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.translate_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.translate_api_key
        self.timeout = timeout or settings.translate_timeout_seconds
        self.default_target = default_target or settings.translate_default_target
        self.default_mode = default_mode or settings.translate_default_mode
        if not self.base_url or not self.api_key:
            raise TranslationError("translate.base_url 或 translate.api_key 未配置")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def translate(
        self,
        text: str,
        source: str = "auto",
        target: str | None = None,
        mode: str | None = None,
        format: str = "text",
    ) -> str:
        """POST ``/v1/translate``; return the ``translation`` text.

        ``target`` / ``mode`` default to the client's ``default_target`` /
        ``default_mode`` (from config). Raises :class:`TranslationError` on HTTP
        non-2xx, network error, or timeout.
        """
        payload = {
            "text": text,
            "source": source,
            "target": target or self.default_target,
            "mode": mode or self.default_mode,
            "format": format,
        }
        try:
            r = httpx.post(
                f"{self.base_url}/v1/translate",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise TranslationError(
                f"翻译请求超时（{self.timeout}s）：{exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise TranslationError(f"调用翻译服务失败: {exc}") from exc
        if r.status_code >= 400:
            raise TranslationError(f"翻译服务返回 {r.status_code}: {r.text[:300]}")
        try:
            body = r.json()
        except ValueError as exc:
            raise TranslationError(f"翻译响应非 JSON: {r.text[:300]}") from exc
        translation = body.get("translation")
        if not isinstance(translation, str):
            raise TranslationError(f"翻译响应缺少 translation 字段: {r.text[:300]}")
        return translation

    def health(self) -> bool:
        """``GET /health`` -> True if the service reports ok (best-effort)."""
        try:
            r = httpx.get(
                f"{self.base_url}/health",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            _logger.warning("翻译服务健康检查失败: %s", exc)
            return False
        if r.status_code >= 400:
            return False
        try:
            return r.json().get("status") == "ok"
        except ValueError:
            return False
