"""Authentication endpoints: login, current user, logout."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user
from ..core.security import (
    allowed_pages,
    create_access_token,
    sync_users_from_password_file,
    verify_password,
)
from ..models.user import User
from ..schemas.auth import LoginRequest, MeResponse, TokenResponse
from ..schemas.user import UserOut

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Sync password.txt first so new/changed users are picked up on login.
    sync_users_from_password_file(db)
    user = db.query(User).filter(User.username == req.username).first()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
    token = create_access_token(user.username, user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
        pages=allowed_pages(user),
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user=UserOut.model_validate(user), pages=allowed_pages(user))


@router.post("/logout")
def logout() -> dict[str, str]:
    # Tokens are stateless (JWT); the client simply discards the token.
    return {"detail": "已登出"}
