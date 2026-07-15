"""User / permission management endpoints (admin only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_admin
from ..core.pages import (
    ADMIN_ONLY_PAGE_KEYS,
    GRANTABLE_PAGE_KEYS,
    PAGE_DEFINITIONS,
)
from ..models.user import PagePermission, User
from ..schemas.user import PageDefinition, UpdatePermissionsRequest, UserOut

router = APIRouter(prefix="/api/users", tags=["权限管理"])


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.get("/pages", response_model=list[PageDefinition])
def list_page_definitions(_: User = Depends(require_admin)):
    """Return all page definitions (used by the permission config dialog)."""
    return [PageDefinition(**p) for p in PAGE_DEFINITIONS]  # type: ignore[arg-type]


@router.get("/{user_id}/permissions", response_model=list[str])
def get_permissions(
    user_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "admin":
        return list(GRANTABLE_PAGE_KEYS) + sorted(ADMIN_ONLY_PAGE_KEYS)
    return [p.page_key for p in user.permissions if p.page_key in GRANTABLE_PAGE_KEYS]


@router.put("/{user_id}/permissions", response_model=list[str])
def set_permissions(
    user_id: int,
    req: UpdatePermissionsRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="管理员默认拥有全部权限，无需配置"
        )
    # Only grantable keys are accepted; drop anything else silently.
    wanted = {k for k in req.page_keys if k in GRANTABLE_PAGE_KEYS}
    db.query(PagePermission).filter(PagePermission.user_id == user_id).delete()
    for key in wanted:
        db.add(PagePermission(user_id=user_id, page_key=key))
    db.commit()
    return sorted(wanted)
