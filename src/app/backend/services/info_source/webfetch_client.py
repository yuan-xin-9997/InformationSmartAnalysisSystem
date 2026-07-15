"""Client for the centralized WebFetch service (CLAUDE.md 网页抓取服务).

Service contract (from its README):
- Base URL + ``Authorization: Bearer <api_key>`` header.
- ``POST /v1/fetch``  body ``{"url","mode":"http|browser|auto","save_artifact":true}``
- ``GET  /v1/artifacts/{id}`` returns the saved raw response.

The exact response schema is parsed defensively (several common key names) so
the client is robust to minor service-side changes. Tests mock this class.
"""
from __future__ import annotations

from typing import Any

import httpx

from ...core.config import settings
from ...core.logging import get_logger

_logger = get_logger("webfetch")

_HTML_KEYS = ("html", "text", "body", "content")
_NESTED_KEYS = ("result", "data", "response")


class WebFetchError(RuntimeError):
    pass


class WebFetchClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.web_fetch_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.web_fetch_api_key
        self.timeout = timeout or settings.web_fetch_timeout
        if not self.base_url:
            raise WebFetchError("web_fetch.base_url 未配置")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def fetch(self, url: str, mode: str = "auto", save_artifact: bool = True) -> dict[str, Any]:
        """POST /v1/fetch and return the parsed JSON response."""
        payload = {"url": url, "mode": mode, "save_artifact": save_artifact}
        try:
            r = httpx.post(
                f"{self.base_url}/v1/fetch",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise WebFetchError(f"调用 web_fetch 失败: {exc}") from exc
        if r.status_code >= 400:
            raise WebFetchError(f"web_fetch 返回 {r.status_code}: {r.text[:200]}")
        return r.json()

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        try:
            r = httpx.get(
                f"{self.base_url}/v1/artifacts/{artifact_id}",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise WebFetchError(f"读取 artifact 失败: {exc}") from exc
        if r.status_code >= 400:
            raise WebFetchError(f"artifact 返回 {r.status_code}: {r.text[:200]}")
        return r.json()

    def fetch_html(self, url: str, mode: str = "auto") -> str:
        """Fetch a URL and extract its HTML text from the service response."""
        resp = self.fetch(url, mode=mode, save_artifact=True)
        html = _extract_text(resp)
        if html:
            return html
        artifact_id = resp.get("artifact_id") or resp.get("artifactId")
        if artifact_id:
            html = _extract_text(self.get_artifact(str(artifact_id)))
            if html:
                return html
        _logger.warning("无法从 web_fetch 响应提取 HTML: %s", str(resp)[:300])
        raise WebFetchError("无法从 web_fetch 响应中提取 HTML 内容")


def _extract_text(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None
    for key in _HTML_KEYS:
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v
    for key in _NESTED_KEYS:
        nested = obj.get(key)
        if isinstance(nested, dict):
            for k in _HTML_KEYS:
                v = nested.get(k)
                if isinstance(v, str) and v.strip():
                    return v
    return None
