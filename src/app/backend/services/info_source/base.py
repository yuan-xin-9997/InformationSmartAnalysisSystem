"""Adapter abstract base + shared data classes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InfoItemData:
    """A fetched item, before persistence. Adapter-agnostic."""

    external_id: str  # stable per source (URL / file path / FreshRSS item id)
    title: str = ""
    url: str | None = None
    content: str = ""
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceStatus:
    """Result of an adapter health check."""

    ok: bool
    message: str = ""
    item_count: int = 0  # items currently available from the source (if known)


class InfoSourceAdapter(ABC):
    """Common interface for all information-source types."""

    type: str = ""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def check_status(self) -> SourceStatus:
        """Probe the source; return health + (optionally) item count."""

    @abstractmethod
    def fetch_new_items(self, since: datetime | None = None) -> list[InfoItemData]:
        """Fetch items newer than ``since`` (None = all)."""

    @staticmethod
    def required_config_keys() -> list[str]:
        return []
