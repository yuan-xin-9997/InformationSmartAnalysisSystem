"""User / permission schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase


class UserOut(ORMBase):
    id: int
    username: str
    role: str
    created_at: BeijingDatetime


class PagePermissionOut(ORMBase):
    id: int
    user_id: int
    page_key: str


class UpdatePermissionsRequest(ORMBase):
    page_keys: list[str]


class PageDefinition(ORMBase):
    key: str
    label: str
    grantable: bool
