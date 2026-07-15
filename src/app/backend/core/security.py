"""Authentication helpers: password hashing, JWT, password.txt sync."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.logging import get_logger
from ..core.pages import GRANTABLE_PAGE_KEYS
from ..models.user import PagePermission, User

_logger = get_logger("security")

# Default page keys granted to a brand-new normal user on first sync.
_DEFAULT_USER_PAGES = ["dashboard"]

ALGORITHM = "HS256"


# --------------------------------------------------------------------------- #
# Password hashing (bcrypt)
# --------------------------------------------------------------------------- #
def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _fingerprint(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# password.txt parsing & sync
# --------------------------------------------------------------------------- #
def parse_password_file(path: Path) -> list[tuple[str, str, str]]:
    """Parse ``username:password:role`` lines (comments start with ``#``).

    Robust to ``:`` inside the password field. Returns ``(username, password,
    role)`` tuples. Missing file -> empty list.
    """
    entries: list[tuple[str, str, str]] = []
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        username = parts[0].strip()
        role = parts[-1].strip()
        password = ":".join(parts[1:-1])
        if not username or not password:
            continue
        if role not in ("admin", "user"):
            role = "user"
        entries.append((username, password, role))
    return entries


def sync_users_from_password_file(db: Session) -> int:
    """Upsert users from ``password.txt``.

    Returns the number of users created or updated. New normal users get a
    default page set (``dashboard``). Existing users keep their permissions.
    Satisfies CLAUDE.md: editing password.txt syncs new users on next login.
    """
    entries = parse_password_file(settings.password_file)
    changed = 0
    for username, password, role in entries:
        fp = _fingerprint(password)
        existing = db.query(User).filter(User.username == username).first()
        if existing is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                password_fingerprint=fp,
                role=role,
            )
            if role == "user":
                for key in _DEFAULT_USER_PAGES:
                    user.permissions.append(PagePermission(page_key=key))
            db.add(user)
            changed += 1
        else:
            dirty = False
            if existing.password_fingerprint != fp:
                existing.password_hash = hash_password(password)
                existing.password_fingerprint = fp
                dirty = True
            if existing.role != role:
                existing.role = role
                dirty = True
            if dirty:
                changed += 1
    if changed:
        db.commit()
        _logger.info("password.txt 同步完成: %d 个用户新增或更新", changed)
    return changed


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.auth_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


# --------------------------------------------------------------------------- #
# Permission helpers
# --------------------------------------------------------------------------- #
def allowed_pages(user: User) -> list[str]:
    """Page keys the user may access (admin -> all)."""
    if user.role == "admin":
        return list(GRANTABLE_PAGE_KEYS) + ["permission"]
    return [p.page_key for p in user.permissions if p.page_key in GRANTABLE_PAGE_KEYS]
