"""Shared schema helpers.

``BeijingDatetime`` serializes any datetime field to Beijing time (ISO 8601)
in API responses, satisfying CLAUDE.md 规范2 (display Beijing time).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from ..core.timeutil import iso_beijing

# Serializes to Beijing-time ISO string; None stays None.
BeijingDatetime = Annotated[
    datetime,
    PlainSerializer(lambda v: iso_beijing(v), return_type=str | None),
]


class ORMBase(BaseModel):
    """Base for schemas that read from ORM models."""

    model_config = ConfigDict(from_attributes=True)
