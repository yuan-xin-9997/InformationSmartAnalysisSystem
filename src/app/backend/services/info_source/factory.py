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
    if source_type == "website" and "sites" in config:
        sites = config["sites"]
        if not isinstance(sites, list) or not sites:
            raise ValueError("sites 必须是非空数组")
        seen = set()
        for site in sites:
            if not isinstance(site, dict) or not isinstance(site.get("name"), str) or not site["name"].strip() or not isinstance(site.get("url"), str) or not site["url"].startswith(("http://", "https://")):
                raise ValueError("每个网站必须提供名称和 http(s) 资讯栏目 URL")
            if site["url"] in seen:
                raise ValueError("网站 URL 不可重复")
            seen.add(site["url"])
            if site.get("mode", "auto") not in ("auto", "http", "browser"):
                raise ValueError("mode 必须为 auto、http 或 browser")
            if "max_items" in site and (not isinstance(site["max_items"], int) or not 1 <= site["max_items"] <= 500):
                raise ValueError("max_items 必须在 1 到 500 之间")
        return
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
