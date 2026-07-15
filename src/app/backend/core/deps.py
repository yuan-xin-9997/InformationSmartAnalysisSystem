"""FastAPI dependencies: current user, role/page authorization."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.pages import ADMIN_ONLY_PAGE_KEYS
from ..core.security import allowed_pages, decode_access_token
from ..models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未认证或认证已过期",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _credentials_exc
    payload = decode_access_token(token)
    if not payload:
        raise _credentials_exc
    username = payload.get("sub")
    if not username:
        raise _credentials_exc
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise _credentials_exc
    return user


def require_role(*roles: str):
    """Dependency factory: require the current user to have one of ``roles``."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return _dep


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def user_has_page(user: User, page_key: str) -> bool:
    if user.role == "admin":
        return True
    if page_key in ADMIN_ONLY_PAGE_KEYS:
        return False
    return any(p.page_key == page_key for p in user.permissions)


def require_page(page_key: str):
    """Dependency factory: require the current user to have ``page_key`` access."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if not user_has_page(user, page_key):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该页面")
        return user

    return _dep


__all__ = [
    "get_current_user",
    "require_role",
    "require_admin",
    "require_page",
    "user_has_page",
    "allowed_pages",
]
