"""Adapter factory + config validation."""
from __future__ import annotations

from typing import Any

from .base import InfoSourceAdapter
from .freshrss import FreshRSSAdapter
from .local_folder import LocalFolderAdapter
from .website import WebsiteAdapter

_ADAPTERS: dict[str, type[InfoSourceAdapter]] = {
    "website": WebsiteAdapter,
    "local_folder": LocalFolderAdapter,
    "freshrss": FreshRSSAdapter,
}

SUPPORTED_TYPES: list[str] = list(_ADAPTERS.keys())


def type_specs() -> list[dict]:
    """Return ``[{type, required_keys}]`` for the frontend source form."""
    return [
        {"type": t, "required_keys": cls.required_config_keys()}
        for t, cls in _ADAPTERS.items()
    ]


def validate_config(source_type: str, config: dict[str, Any]) -> None:
    """Raise ``ValueError`` if ``config`` is missing required keys."""
    cls = _ADAPTERS.get(source_type)
    if cls is None:
        raise ValueError(f"不支持的信息源类型: {source_type}")
    if not isinstance(config, dict):
        raise ValueError("config 必须是对象")
    missing = [k for k in cls.required_config_keys() if not config.get(k)]
    if missing:
        raise ValueError(f"配置缺少必填字段: {', '.join(missing)}")


def get_adapter(source_type: str, config: dict[str, Any], **kwargs: Any) -> InfoSourceAdapter:
    """Instantiate the adapter for ``source_type``."""
    cls = _ADAPTERS.get(source_type)
    if cls is None:
        raise ValueError(f"不支持的信息源类型: {source_type}")
    validate_config(source_type, config)
    # WebsiteAdapter accepts an optional web_fetch_client kwarg.
    return cls(config, **kwargs)
