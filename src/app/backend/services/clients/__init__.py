"""External HTTP service clients (CLAUDE.md 架构要求 4/5).

Hosts thin clients for the NAS-hosted local services:
- :class:`OCRClient` -- local OCR service (ollama / ``glm-ocr``).
- :class:`TranslationClient` -- local translation service (ollama / ``translategemma``).

Both use ``Authorization: Bearer <api_key>`` auth, configurable via the ``ocr`` /
``translate`` blocks in ``config/app.json`` (``ISAS_OCR_*`` / ``ISAS_TRANSLATE_*``
env overrides).
"""
from __future__ import annotations

from .ocr_client import OCRClient, OCRError
from .translation_client import TranslationClient, TranslationError

__all__ = [
    "OCRClient",
    "OCRError",
    "TranslationClient",
    "TranslationError",
]
