"""Information-source schemas."""
from __future__ import annotations

from typing import Literal

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


class InfoItemFigureOut(ORMBase):
    """A figure belonging to an InfoItem, as returned by the results API."""

    index: int            # corresponds to InfoItemFigure.figure_index
    url: str              # /api/info-sources/{source_id}/items/{item_id}/figures/{index}
    mime: str | None
    width: int | None
    height: int | None


class SourceFileOut(ORMBase):
    """Source-file info attached to a per_item analysis result.

    Lets the result page render file/metadata/figures in one fetch.
    `aggregate` results have no single file, so their ``source_file`` is null.
    """

    filename: str                 # InfoItem.title (local_folder: filename)
    file_path: str                # InfoItem.external_id (resolved absolute path)
    title: str                    # InfoItem.title
    author: str | None
    author_affiliation: str | None
    published_at: BeijingDatetime | None
    page_count: int | None
    extraction_method: str | None = None  # text_layer | vision_llm | none
    file_url: str                 # /api/info-sources/{source_id}/items/{item_id}/file
    figures: list[InfoItemFigureOut] = []


class ItemsQueryRequest(ORMBase):
    source_ids: list[int]
    limit: int = 50
    offset: int = 0
    analyzed: bool | None = None
    # 选择条目弹窗增强：已选取数 / 排除已选 / 列排序 / 关键词筛选（均可选，向后兼容）
    ids: list[int] | None = None
    exclude_ids: list[int] | None = None
    sort_by: str | None = None
    order: Literal["asc", "desc"] = "desc"
    keyword: str | None = None


class ItemsQueryResponse(ORMBase):
    items: list[InfoItemBrief]
    total: int


class SourceStatusOut(ORMBase):
    status: str
    message: str
    item_count: int
    last_sync_at: BeijingDatetime | None
