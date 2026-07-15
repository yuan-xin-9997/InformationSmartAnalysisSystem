"""Auth schemas."""
from __future__ import annotations

from .common import BeijingDatetime, ORMBase
from .user import UserOut


class LoginRequest(ORMBase):
    username: str
    password: str


class TokenResponse(ORMBase):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    pages: list[str]


class MeResponse(ORMBase):
    user: UserOut
    pages: list[str]
