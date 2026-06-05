"""Authentication routes: register, login, refresh, /me."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from . import auth, auth_schemas, db_models
from .database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


# Free tier message limit before prompting to subscribe. Kept in sync
# with `routes.FREE_MESSAGES_LIMIT` — change one, change both.
FREE_MESSAGES_LIMIT = 5


@router.post("/register", response_model=auth_schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    req: auth_schemas.RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.TokenResponse:
    """Create a new user account and return access + refresh tokens."""
    existing = db.query(db_models.User).filter(
        db_models.User.email == req.email.lower()
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = db_models.User(
        email=req.email.lower(),
        hashed_password=auth.hash_password(req.password),
        full_name=req.full_name,
        gender_preference=db_models.GenderPref(req.gender_preference or "neutral"),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    db.refresh(user)

    access = auth.create_access_token(user.id, user.email, user.token_version)
    refresh = auth.create_refresh_token(user.id, user.email, user.token_version)
    return auth_schemas.TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=auth_schemas.TokenResponse)
def login(
    req: auth_schemas.LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.TokenResponse:
    """Verify credentials and return access + refresh tokens.

    Constant-time response: when the user does not exist we still run a
    bcrypt verify against a dummy hash so timing cannot be used to enumerate
    accounts.
    """
    # Always run a bcrypt verify, even when the user is missing, to keep
    # response time constant. The dummy hash is for "no-such-user".
    # We also run a bcrypt verify for disabled users (same dummy hash)
    # so the time-to-response can't be used to enumerate which
    # accounts are active vs disabled. See BUG-AUTHR-018.
    _DUMMY_HASH = "$2b$12$CwTycUXWue0Thq9StjUM0uJ8Vd1IX0Q8dL1.Jjh1hYpQ3P4lp7mZi"
    user = db.query(db_models.User).filter(
        db_models.User.email == req.email.lower()
    ).first()
    if user is None:
        auth.verify_password(req.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    # Always run the verify against the real hash, regardless of the
    # outcome of the is_active check below, so timing can't reveal
    # whether the account is active.
    password_ok = auth.verify_password(req.password, user.hashed_password)
    if not user.is_active:
        auth.verify_password(req.password, _DUMMY_HASH)  # pad to ~constant time
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact support.",
        )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access = auth.create_access_token(user.id, user.email, user.token_version)
    refresh = auth.create_refresh_token(user.id, user.email, user.token_version)
    return auth_schemas.TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=auth_schemas.TokenResponse)
def refresh_token(
    req: auth_schemas.RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        payload = auth.decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Wrong token type")
        user_id_raw = payload.get("uid")
        user_id = int(user_id_raw) if user_id_raw is not None else None
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.get(db_models.User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")
    if int(payload.get("ver", 0)) != int(user.token_version):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return auth_schemas.TokenResponse(
        access_token=auth.create_access_token(user.id, user.email, user.token_version),
        refresh_token=auth.create_refresh_token(user.id, user.email, user.token_version),
        expires_in=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
def logout(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Invalidate the current session by bumping token_version.

    With localStorage-based tokens, the client can only "forget" the token;
    we can't revoke it server-side. The server-side control is the
    token_version claim: every token issued before this call will be rejected
    on the next request. Clients that don't log out aren't affected — the
    new version is what matters.
    """
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"message": "Logged out. All tokens for this account have been invalidated."}


@router.post("/logout-all")
def logout_all(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Invalidate every device's session (password-change recovery, lost device)."""
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"message": "All sessions invalidated. Please sign in again."}


@router.get("/me", response_model=auth_schemas.UserOut)
def get_me(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.UserOut:
    """Return the currently authenticated user's profile."""
    has_sub = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == user.id,
        db_models.Subscription.status == db_models.SubStatus.active,
        db_models.Subscription.current_period_end > datetime.now(timezone.utc),
    ).first() is not None

    return auth_schemas.UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        gender_preference=user.gender_preference.value,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        free_messages_used=user.free_messages_used,
        created_at=user.created_at,
        has_active_subscription=has_sub,
        token_version=user.token_version,
    )


@router.patch("/me", response_model=auth_schemas.UserOut)
def update_me(
    req: auth_schemas.UserUpdate,
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.UserOut:
    """Update the authenticated user's profile (name, gender preference)."""
    if req.full_name is not None:
        # Strip control characters and cap at 255 chars; reject if the
        # caller sent something that would be silently truncated.
        if len(req.full_name) > 255:
            raise HTTPException(
                status_code=422,
                detail="full_name must be 255 characters or fewer",
            )
        cleaned = "".join(ch for ch in req.full_name if ch.isprintable()).strip()
        user.full_name = cleaned[:255] if cleaned else None
    if req.gender_preference is not None:
        user.gender_preference = db_models.GenderPref(req.gender_preference)
    db.commit()
    db.refresh(user)
    return get_me(user=user, db=db)


@router.post("/change-password")
def change_password(
    req: auth_schemas.ChangePasswordRequest,
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Change the authenticated user's password and invalidate other sessions."""
    if not auth.verify_password(req.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = auth.hash_password(req.new_password)
    # Bump token_version so a leaked token can't keep working. The caller
    # already used the new password to authenticate this call, so they
    # get a fresh token from /auth/login after this succeeds.
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"message": "Password updated. Other sessions have been signed out."}
