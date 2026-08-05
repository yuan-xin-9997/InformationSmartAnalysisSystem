"""Client for the NAS local OCR service (CLAUDE.md 架构要求 5).

Service contract (from its OpenAPI at ``/docs``):
- Base URL + ``Authorization: Bearer <api_key>`` header.
- ``POST /v1/ocr``  multipart form: ``file`` (image octet-stream, required),
  ``mode`` (text|markdown|table|formula, default ``text``),
  ``language`` (default ``auto``).
- Response JSON: ``{"text": str, "model": str, "mode": str, "pages": int,
  "processing_seconds": float, "page_results": [{"page": int, "text": str}]}``.
- ``GET /health`` -> ``{"status": "ok", ...}``.

Used by the PDF vision-fallback extraction (``local_folder._vision_extract_pdf``)
when the PDF text layer is empty/garbled. The caller renders each page to a PNG
and calls :meth:`OCRClient.ocr` per page; this client never raises out of the
extraction path on failure -- callers wrap calls in try/except and degrade.
"""
from __future__ import annotations

from typing import Any

import httpx

from ...core.config import settings
from ...core.logging import get_logger

_logger = get_logger("ocr")


class OCRError(RuntimeError):
    pass


class OCRClient:
    """Calls the local OCR service ``POST /v1/ocr`` (multipart image upload)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        mode: str | None = None,
        language: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ocr_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.ocr_api_key
        self.timeout = timeout or settings.ocr_timeout_seconds
        self.mode = mode or settings.ocr_mode
        self.language = language or settings.ocr_language
        if not self.base_url or not self.api_key:
            raise OCRError("ocr.base_url 或 ocr.api_key 未配置")

    def _headers(self) -> dict[str, str]:
        # NOTE: do NOT set Content-Type here; httpx sets the multipart boundary.
        return {"Authorization": f"Bearer {self.api_key}"}

    def ocr(
        self,
        image_bytes: bytes,
        filename: str | None = None,
        mode: str | None = None,
        language: str | None = None,
    ) -> str:
        """POST ``/v1/ocr`` with one image; return the extracted ``text``.

        Raises :class:`OCRError` on HTTP non-2xx, network error, or timeout.
        Never returns a partial result.
        """
        files = {"file": (filename or "page.png", image_bytes, "image/png")}
        data = {"mode": mode or self.mode, "language": language or self.language}
        try:
            r = httpx.post(
                f"{self.base_url}/v1/ocr",
                files=files,
                data=data,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise OCRError(
                f"OCR 请求超时（{self.timeout}s）：{exc}。"
                "glm-ocr 首次推理冷启动较慢，可适当调大 ocr.timeout_seconds。"
            ) from exc
        except httpx.HTTPError as exc:
            raise OCRError(f"调用 OCR 服务失败: {exc}") from exc
        if r.status_code >= 400:
            raise OCRError(f"OCR 返回 {r.status_code}: {r.text[:300]}")
        try:
            payload: dict[str, Any] = r.json()
        except ValueError as exc:
            raise OCRError(f"OCR 响应非 JSON: {r.text[:300]}") from exc
        text = payload.get("text")
        if not isinstance(text, str):
            raise OCRError(f"OCR 响应缺少 text 字段: {r.text[:300]}")
        return text

    def health(self) -> bool:
        """``GET /health`` -> True if the service reports ok (best-effort)."""
        try:
            r = httpx.get(
                f"{self.base_url}/health",
                headers=self._headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            _logger.warning("OCR 健康检查失败: %s", exc)
            return False
        if r.status_code >= 400:
            return False
        try:
            return r.json().get("status") == "ok"
        except ValueError:
            return False
