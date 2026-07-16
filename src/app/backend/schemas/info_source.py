"""Information-source schemas."""
from __future__ import annotations

from pydantic import field_serializer

from ..core.secrets import mask_sensitive
from .common import BeijingDatetime, ORMBase


class InfoSourceOut(ORMBase):
    id: int
    name: str
    type: str
    config: dict
    status: str
    last_sync_at: BeijingDatetime | None
    last_error: str | None
    item_count: int
    created_at: BeijingDatetime
    updated_at: BeijingDatetime

    @field_serializer("config")
    def _mask_config(self, v: dict) -> dict:
        return mask_sensitive(v) if v else v


class InfoSourceCreate(ORMBase):
    name: str
    type: str
    config: dict


class InfoSourceUpdate(ORMBase):
    name: str | None = None
    config: dict | None = None


class InfoItemBrief(ORMBase):
    id: int
    source_id: int
    external_id: str
    title: str
    url: str | None
    published_at: BeijingDatetime | None
    fetched_at: BeijingDatetime
    analyzed: bool
    created_at: BeijingDatetime


class InfoItemOut(InfoItemBrief):
    content: str


class ItemsQueryRequest(ORMBase):
    source_ids: list[int]
    limit: int = 50
    offset: int = 0
    analyzed: bool | None = None


class ItemsQueryResponse(ORMBase):
    items: list[InfoItemBrief]
    total: int


class SourceStatusOut(ORMBase):
    status: str
    message: str
    item_count: int
    last_sync_at: BeijingDatetime | None
