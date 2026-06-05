"""Authentication utilities: JWT tokens, password hashing, and FastAPI dependencies.

JWT-based auth: users get an access token (short-lived) and refresh token (longer).
Tokens carry only the user id and email - no sensitive data.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import db_models
from .database import get_db

log = logging.getLogger(__name__)


# ---- Configuration ----
# Default secrets are intentionally non-production. validate_secrets() refuses
# to start in production if the dev defaults are still in use. Tests set
# ALLOW_INSECURE_DEFAULTS=1 to skip validation.
_DEV_JWT_SECRET = "dev-secret-change-in-prod-use-openssl-rand-base64-32"
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", _DEV_JWT_SECRET)
# Algorithm allow-list. We never honour `none`, never RS256-with-public-key
# (this app is single-tenant so HS* is fine), and never anything the
# jose library doesn't support. See L5 in the audit.
_ALLOWED_ALGS = {"HS256", "HS384", "HS512"}
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
if JWT_ALGORITHM not in _ALLOWED_ALGS:
    raise RuntimeError(
        f"JWT_ALGORITHM={JWT_ALGORITHM!r} is not in the allow-list "
        f"{sorted(_ALLOWED_ALGS)}. Edit auth.py to add a new algorithm."
    )
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


# ---- Password hashing ----
#
# bcrypt silently truncates passwords longer than 72 bytes. To avoid
# surprising users (and to keep our verify path consistent), we
# pre-hash long passwords with SHA-256 (hex-encoded, 64 chars) and
# pass that to bcrypt. The result is a deterministic 60-char bcrypt
# hash of a 64-char hex string — no silent truncation.
#
# For passwords up to 72 bytes we pass them through unchanged so the
# hash format is familiar to anyone inspecting the DB.
import hashlib

_BCRYPT_MAX_BYTES = 72


def _bcrypt_safe(password: str) -> str:
    """Return a form of `password` that bcrypt can consume without
    silently truncating it. See module docstring above for rationale."""
    encoded = password.encode("utf-8")
    if len(encoded) <= _BCRYPT_MAX_BYTES:
        return password
    return hashlib.sha256(encoded).hexdigest()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(_bcrypt_safe(plain))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_bcrypt_safe(plain), hashed)


# ---- JWT ----
def _create_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "jti": secrets.token_urlsafe(16)})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: int, email: str, token_version: int = 0) -> str:
    return _create_token(
        {"sub": str(user_id), "uid": user_id, "type": "access", "ver": token_version},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int, email: str, token_version: int = 0) -> str:
    return _create_token(
        {"sub": str(user_id), "uid": user_id, "type": "refresh", "ver": token_version},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid/expired tokens.

    Accepts a 30-second clock skew on `exp`/`nbf`/`iat` so small
    differences between the issuing and verifying server don't cause
    spurious 401s. See H3 in the audit.
    """
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"leeway": 30},
    )


# ---- FastAPI dependencies ----
# `HTTPBearer` extracts the token from the `Authorization: Bearer <token>` header.
# auto_error=False lets us raise our own HTTPException with a custom message.
security = HTTPBearer(auto_error=False)


def _credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _disabled_exception(detail: str = "Account is disabled") -> HTTPException:
    # 403 (not 401) when the token is otherwise valid but the user has
    # been deactivated. The frontend treats 401 as "force re-login" and
    # 403 as "show error". Mixing them caused an infinite redirect
    # loop. See audit #25.
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail,
    )


def _user_from_payload(payload: dict, db: Session) -> tuple[Optional[db_models.User], Optional[str]]:
    """Shared lookup used by get_current_user / get_optional_user.

    Returns (user, reason). On success, reason is None. On failure, user is None and
    reason is one of:
      - "user_not_found": the user_id in the token doesn't exist
      - "stale_token": the token_version is stale (logout-everywhere, password change)
      - "disabled": the user is_active=False (deactivated by admin)
    Rejecting these distinctly lets get_current_user raise 401 vs 403
    appropriately. See audit #25.
    """
    if payload.get("type") != "access":
        return None, "user_not_found"
    user_id = payload.get("uid")
    if user_id is None:
        return None, "user_not_found"
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None, "user_not_found"
    user = db.get(db_models.User, user_id)
    if user is None:
        return None, "user_not_found"
    if not user.is_active:
        return None, "disabled"
    if int(payload.get("ver", 0)) != int(getattr(user, "token_version", 0)):
        return None, "stale_token"
    return user, None


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> db_models.User:
    """FastAPI dependency: returns the authenticated user or raises 401/403."""
    if creds is None:
        raise _credentials_exception("Missing authentication token")
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        raise _credentials_exception("Invalid or expired token")
    user, reason = _user_from_payload(payload, db)
    if user is None:
        if reason == "disabled":
            raise _disabled_exception("Account is disabled")
        raise _credentials_exception("Invalid or expired token")
    return user


async def get_optional_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[db_models.User]:
    """Like get_current_user but returns None instead of raising on missing token.
    Useful for endpoints that work for both anonymous and authenticated users."""
    if creds is None:
        return None
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        return None
    user, _reason = _user_from_payload(payload, db)
    return user


async def require_admin(
    user: db_models.User = Depends(get_current_user),
) -> db_models.User:
    """FastAPI dependency: ensures the caller is an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


# ---- Startup validation ----
def validate_secrets(allow_insecure: bool = False) -> None:
    """Refuse to start with weak / default secrets in production.

    Call this from main.py on startup. If any check fails we log a loud warning;
    in production (ENVIRONMENT=production) we raise to abort boot.
    """
    env = os.environ.get("ENVIRONMENT", "development").lower()
    insecure = False
    problems: list[str] = []

    # 1. JWT secret must be set, not the dev value, and at least 32 bytes.
    if JWT_SECRET_KEY == _DEV_JWT_SECRET:
        problems.append("JWT_SECRET_KEY is the dev default. Set a 32+ byte random value.")
        insecure = True
    elif len(JWT_SECRET_KEY.encode("utf-8")) < 32:
        problems.append(f"JWT_SECRET_KEY is only {len(JWT_SECRET_KEY)} bytes; minimum is 32.")
        insecure = True

    # 2. ADMIN_API_KEY must be set and not the dev default.
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    if admin_key == "" or admin_key == "dev-secret-change-in-prod":
        problems.append("ADMIN_API_KEY is unset or the dev default.")
        insecure = True
    elif len(admin_key.encode("utf-8")) < 16:
        problems.append(f"ADMIN_API_KEY is only {len(admin_key)} bytes; minimum is 16.")
        insecure = True

    if not problems:
        return

    if insecure and env == "production" and not allow_insecure:
        raise RuntimeError(
            "Refusing to start in production with insecure secrets:\n  - "
            + "\n  - ".join(problems)
            + "\nGenerate strong values with: openssl rand -base64 32"
        )

    for p in problems:
        log.warning("INSECURE CONFIG: %s", p)
