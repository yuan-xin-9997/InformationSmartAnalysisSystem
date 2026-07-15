"""Sensitive-value masking for API responses (CLAUDE.md 规范1)."""
from __future__ import annotations

import re

_SENSITIVE = re.compile(r"(secret|password|token|api[_-]?key)", re.IGNORECASE)


def mask_value(v: str) -> str:
    tail = v[-4:]
    return "******" + tail if (tail and tail.isascii() and tail.isalnum()) else "******"


def mask_sensitive(obj):
    """Recursively mask values whose key looks sensitive."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str) and _SENSITIVE.search(k) and v:
                out[k] = mask_value(v)
            else:
                out[k] = mask_sensitive(v)
        return out
    if isinstance(obj, list):
        return [mask_sensitive(x) for x in obj]
    return obj
