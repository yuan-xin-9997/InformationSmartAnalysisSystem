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
    def fetch_new_items(
        self,
        since: datetime | None = None,
        known_ids: set[str] | None = None,
    ) -> list[InfoItemData]:
        """Fetch items to sync.

        ``since`` is the source's last sync time; ``known_ids`` are external ids
        already stored. Adapters should return items that are **newer than
        ``since`` OR not in ``known_ids``** (incremental + backfill), so that:

        - first sync (``since=None``, empty ``known_ids``) returns everything;
        - subsequent syncs skip known-unchanged items (no re-read) and only
          return new / modified / not-yet-backed-filled items.
        """

    @staticmethod
    def required_config_keys() -> list[str]:
        return []
