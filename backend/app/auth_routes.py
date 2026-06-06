"""Authentication routes: register, login, refresh, /me, change-password,
logout, forgot-password, reset-password, verify-email, delete-account,
avatar, last-login tracking, admin JWT login."""
from __future__ import annotations

import base64
import binascii
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from . import auth, auth_schemas, db_models, utils
from .database import get_db

log = logging.getLogger(__name__)

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

    # Welcome notification (in-app bell + email). Failure here is
    # never fatal — the user is created and logged in regardless.
    try:
        from .round9_routes import _create_notification
        _create_notification(
            db, user.id, "system", "Welcome to RoastGPT 🔥",
            f"Hi {user.full_name or 'there'}! Your account is ready. "
            "Pick a mode, pick a personality, and prepare to get roasted.",
            link="/",
        )
    except Exception:
        pass
    # Welcome email
    try:
        utils.send_welcome_email(user.email, user.full_name)
    except Exception:
        pass

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
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.TokenResponse:
    """Verify credentials and return access + refresh tokens.

    Constant-time response: when the user does not exist we still run a
    bcrypt verify against a dummy hash so timing cannot be used to enumerate
    accounts. Also records `last_login_at` / `last_login_ip` and writes an
    audit row.
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
        utils.log_action(
            db, action="login_failed_no_user",
            actor_ip=request.client.host if request.client else None,
            details={"email": req.email.lower()},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    # Always run the verify against the real hash, regardless of the
    # outcome of the is_active check below, so timing can't reveal
    # whether the account is active.
    password_ok = auth.verify_password(req.password, user.hashed_password)
    if user.deleted_at is not None:
        # Soft-deleted account: log a special audit event and refuse.
        utils.log_action(
            db, action="login_failed_deleted",
            actor_user_id=user.id,
            actor_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deleted. Contact support to restore.",
        )
    if user.is_banned:
        utils.log_action(
            db, action="login_failed_banned",
            actor_user_id=user.id,
            actor_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is banned: {user.ban_reason or 'No reason given'}",
        )
    if not user.is_active:
        auth.verify_password(req.password, _DUMMY_HASH)  # pad to ~constant time
        utils.log_action(
            db, action="login_failed_disabled",
            actor_user_id=user.id,
            actor_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact support.",
        )
    if not password_ok:
        utils.log_action(
            db, action="login_failed_wrong_password",
            actor_user_id=user.id,
            actor_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Record last-login for the admin anomaly-detection column.
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = (request.client.host if request.client else None) or None
    db.commit()

    utils.log_action(
        db, action="login_success",
        actor_user_id=user.id,
        actor_ip=user.last_login_ip,
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
    """Exchange a valid refresh token for a new access + refresh token pair.

    ROTATES the refresh token: every successful /refresh bumps
    `token_version`, which invalidates the old refresh token (and any
    access tokens that referenced the prior version). The next call
    with the old refresh token returns 401, which triggers a forced
    re-login on the client. This is the standard mitigation against
    stolen refresh tokens — without rotation, a token leaked via XSS,
    a malicious extension, or a proxy log stays valid for the full
    7-day window even after the user logs out.
    """
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

    # Bump token_version. The OLD refresh token is now invalid
    # (ver mismatch on the next call), as is every access token
    # issued at the old version. A new pair is returned below.
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    db.refresh(user)

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


def _build_user_out(user: db_models.User, db: Session) -> dict:
    """Construct a UserOut dict from a User row, including the optional
    profile fields (avatar, ban status, last login, favorites) that the
    frontend's account page reads. Centralised so /me, PATCH /me,
    /me/avatar, /me/favorites, /auth/login, /auth/register all return
    the same shape — and adding a field is a one-line change here.

    Returns a dict (not a UserOut model instance) so endpoints that
    declare `response_model=UserOut` get the right type, and endpoints
    that don't (like /me/favorites which previously returned only two
    fields) still serialise correctly.
    """
    has_sub = db.query(db_models.Subscription).filter(
        db_models.Subscription.user_id == user.id,
        db_models.Subscription.status == db_models.SubStatus.active,
        db_models.Subscription.current_period_end > datetime.now(timezone.utc),
    ).first() is not None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "gender_preference": user.gender_preference.value,
        "is_verified": user.is_verified,
        "is_admin": user.is_admin,
        "role": user.role,
        "free_messages_used": user.free_messages_used,
        "created_at": user.created_at,
        "has_active_subscription": has_sub,
        "token_version": user.token_version,
        "avatar_url": user.avatar_url,
        "is_banned": user.is_banned,
        "ban_reason": user.ban_reason,
        "banned_at": user.banned_at,
        "last_login_at": user.last_login_at,
        "favorite_mode": user.favorite_mode,
        "favorite_personality": user.favorite_personality,
    }


@router.get("/me", response_model=auth_schemas.UserOut)
def get_me(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.UserOut:
    """Return the currently authenticated user's profile."""
    return _build_user_out(user, db)


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
    # Reject "new == current" — a real phishing/UX trap. The
    # frontend also rejects this, but the backend is the only
    # trustworthy gate.
    if req.new_password == req.current_password:
        raise HTTPException(
            status_code=400,
            detail="New password must be different from current password",
        )
    user.hashed_password = auth.hash_password(req.new_password)
    # Bump token_version so a leaked token can't keep working. The caller
    # already used the new password to authenticate this call, so they
    # get a fresh token from /auth/login after this succeeds.
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    # In-app notification
    try:
        from .round9_routes import _create_notification
        _create_notification(
            db, user.id, "system", "Password changed",
            "Your password was updated. Other sessions have been signed out.",
            link="/account",
        )
    except Exception:
        pass
    return {"message": "Password updated. Other sessions have been signed out."}


# ----- Schemas for the new endpoints -----


from pydantic import BaseModel, EmailStr, Field as PField  # noqa: E402


class _ForgotReq(BaseModel):
    email: EmailStr


class _ResetReq(BaseModel):
    token: str
    new_password: str = PField(min_length=8, max_length=128)


class _VerifyReq(BaseModel):
    token: str


class _AvatarReq(BaseModel):
    # Either an HTTPS URL (e.g. Gravatar, OAuth) or a data URI.
    # Capped at 2 MB raw to prevent storage abuse.
    image: str = PField(min_length=10, max_length=2_500_000)


class _FavoriteReq(BaseModel):
    favorite_mode: Optional[str] = PField(default=None, max_length=32)
    favorite_personality: Optional[str] = PField(default=None, max_length=32)


# ----- Email verification -----


@router.post("/send-verification")
def send_verification(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Issue and email a verification token. Idempotent (a fresh token
    is issued even if a previous one is still live). Rate-limited at
    the route level via the standard 60/min cap.
    """
    if user.is_verified:
        return {"message": "Email already verified"}
    token = utils.issue_email_token(db, user.id, "verify", ttl_seconds=24 * 60 * 60)
    utils.send_verification_email(user.email, token)
    utils.log_action(
        db, action="verification_email_sent",
        actor_user_id=user.id,
        actor_ip=request.client.host if request.client else None,
    )
    return {"message": "Verification email sent"}


@router.post("/verify-email")
def verify_email(
    req: _VerifyReq,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Consume a verification token and flip `is_verified=True`."""
    user = utils.consume_email_token(db, req.token, "verify")
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    user.is_verified = True
    db.commit()
    utils.log_action(
        db, action="email_verified",
        actor_user_id=user.id,
        actor_ip=request.client.host if request.client else None,
    )
    # Unlock the "Verified Human" achievement.
    utils.unlock_achievement(db, user.id, "verified")
    return {"message": "Email verified"}


# ----- Forgot / reset password -----


@router.post("/forgot-password")
def forgot_password(
    req: _ForgotReq,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Always returns 200 with a generic message to prevent email
    enumeration. If the email exists, an actual reset link is sent.
    """
    user = db.query(db_models.User).filter(
        db_models.User.email == req.email.lower(),
        db_models.User.deleted_at.is_(None),
    ).first()
    if user is not None and user.is_active and not user.is_banned:
        token = utils.issue_email_token(db, user.id, "reset", ttl_seconds=60 * 60)
        utils.send_password_reset_email(user.email, token)
        utils.log_action(
            db, action="password_reset_email_sent",
            actor_user_id=user.id,
            actor_ip=request.client.host if request.client else None,
        )
    else:
        utils.log_action(
            db, action="password_reset_email_miss",
            actor_ip=request.client.host if request.client else None,
            details={"email": req.email.lower()},
        )
    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(
    req: _ResetReq,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Consume a reset token and set a new password. Bumps
    token_version so any leaked JWTs become useless."""
    user = utils.consume_email_token(db, req.token, "reset")
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = auth.hash_password(req.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    utils.log_action(
        db, action="password_reset_success",
        actor_user_id=user.id,
        actor_ip=request.client.host if request.client else None,
    )
    return {"message": "Password updated. Please log in with your new password."}


# ----- Delete account (soft delete, GDPR/CCPA) -----


@router.delete("/me", status_code=200)
def delete_my_account(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Soft-delete the authenticated user. The row is retained for
    30 days for support-driven restoration, then hard-deleted by a
    background job. Personal data (email, name, sessions, history)
    is anonymised on hard-delete."""
    user.deleted_at = datetime.now(timezone.utc)
    user.is_active = False
    user.token_version = (user.token_version or 0) + 1  # invalidate sessions
    db.commit()
    utils.log_action(
        db, action="account_soft_deleted",
        actor_user_id=user.id,
        actor_ip=request.client.host if request.client else None,
    )
    return {
        "message": "Your account has been scheduled for deletion. "
                   "Contact support within 30 days to restore."
    }


# ----- Avatar upload (data URI or HTTPS URL) -----


@router.post("/me/avatar")
def set_avatar(
    req: _AvatarReq,
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Set the user's avatar. Accepts either an HTTPS URL or a
    `data:image/...;base64,...` URI (max ~2 MB raw).

    We accept data URIs to keep the deployment stateless — no S3
    bucket to configure on the free tier. A production deployment
    with an S3 bucket should add a multipart upload endpoint.
    """
    val = req.image.strip()
    if val.startswith("data:"):
        # Validate base64 payload.
        try:
            header, b64 = val.split(",", 1)
        except ValueError:
            raise HTTPException(status_code=422, detail="Malformed data URI")
        if ";base64" not in header:
            raise HTTPException(status_code=422, detail="Only base64 data URIs are supported")
        try:
            decoded = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(status_code=422, detail=f"Invalid base64: {e}")
        if len(decoded) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Avatar too large (max 2 MB)")
    elif val.startswith("https://"):
        # OK — treat as remote URL.
        pass
    else:
        raise HTTPException(status_code=422, detail="image must be a data URI or https:// URL")
    user.avatar_url = val
    db.commit()
    utils.unlock_achievement(db, user.id, "avatar_set")
    return {"message": "Avatar updated", "avatar_url": val[:200] + ("…" if len(val) > 200 else "")}


# ----- User statistics (power-user surface) -----


@router.get("/me/stats")
def my_stats(
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Per-user stats: message counts, per-mode/personality score
    breakdown, total/best/average score, days since signup,
    achievements, current streak, weekly rank, and recent topics.

    Response shape matches the frontend `UserStats` interface (see
    `frontend/lib/auth-api.ts`) — `score_by_mode` and
    `score_by_personality` are `{count, total}` maps so the UI can
    render an average inline without a second query.
    """
    from . import db_models
    from sqlalchemy import func as sqlfunc

    mem = db.query(db_models.UserMemory).filter(
        db_models.UserMemory.user_id == user.id
    ).first()
    mode_counts = (mem.mode_counts_json if mem else {}) or {}
    personality_counts = (mem.personality_counts_json if mem else {}) or {}

    unlocked = db.query(db_models.UserAchievement).filter(
        db_models.UserAchievement.user_id == user.id
    ).count()
    achievements_total = db.query(db_models.Achievement).count()

    # Per-mode & per-personality score breakdown. We compute on the fly
    # by joining ChatHistory with the mode/personality on the matching
    # roast_sessions row (mode/personality live on the session, not the
    # chat_history row, because the user can change them mid-session).
    score_by_mode: Dict[str, Dict[str, int]] = {}
    score_by_personality: Dict[str, Dict[str, int]] = {}
    rows = (
        db.query(
            db_models.RoastSession.mode,
            db_models.RoastSession.personality,
            sqlfunc.coalesce(
                sqlfunc.sum(db_models.ChatHistory.score_total), 0.0
            ).label("total"),
            sqlfunc.count(db_models.ChatHistory.id).label("count"),
        )
        .join(db_models.ChatHistory, db_models.ChatHistory.session_id == db_models.RoastSession.session_id)
        .filter(db_models.ChatHistory.user_id == user.id)
        .group_by(db_models.RoastSession.mode, db_models.RoastSession.personality)
        .all()
    )
    for mode, personality, total, count in rows:
        if mode:
            slot = score_by_mode.setdefault(mode, {"count": 0, "total": 0})
            slot["count"] += int(count or 0)
            slot["total"] += int(total or 0)
        if personality:
            slot = score_by_personality.setdefault(personality, {"count": 0, "total": 0})
            slot["count"] += int(count or 0)
            slot["total"] += int(total or 0)

    # Total distinct sessions the user has chatted in.
    total_sessions = (
        db.query(sqlfunc.count(sqlfunc.distinct(db_models.ChatHistory.session_id)))
        .filter(db_models.ChatHistory.user_id == user.id, db_models.ChatHistory.session_id.isnot(None))
        .scalar() or 0
    )

    # Best score: max score_total across all of this user's chat rows.
    best_score = (
        db.query(sqlfunc.coalesce(sqlfunc.max(db_models.ChatHistory.score_total), 0.0))
        .filter(db_models.ChatHistory.user_id == user.id)
        .scalar() or 0.0
    )

    # Recent topics: last 10 distinct (case-insensitive) user messages,
    # most-recent first. Capped at 60 chars to keep the chips short.
    recent_topics_rows = (
        db.query(db_models.ChatHistory.message)
        .filter(
            db_models.ChatHistory.user_id == user.id,
            db_models.ChatHistory.is_user == True,  # noqa: E712
        )
        .order_by(db_models.ChatHistory.created_at.desc())
        .limit(100)
        .all()
    )
    seen = set()
    recent_topics: List[str] = []
    for (msg,) in recent_topics_rows:
        if not msg:
            continue
        s = " ".join(msg.split()).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        recent_topics.append(s[:60])
        if len(recent_topics) >= 10:
            break

    # Weekly rank: how this user compares to other users in the last 7
    # days. Computed in-process (no snapshot dependency) so it's always
    # fresh. Returns None if the user has no chat in the window.
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    user_weekly = (
        db.query(sqlfunc.coalesce(sqlfunc.sum(db_models.ChatHistory.score_total), 0.0))
        .filter(
            db_models.ChatHistory.user_id == user.id,
            db_models.ChatHistory.created_at >= week_start,
        )
        .scalar() or 0.0
    )
    rank: Optional[int] = None
    if user_weekly and user_weekly > 0:
        higher = (
            db.query(sqlfunc.count(sqlfunc.distinct(db_models.ChatHistory.user_id)))
            .filter(
                db_models.ChatHistory.created_at >= week_start,
            )
            .group_by(db_models.ChatHistory.user_id)
            .having(sqlfunc.sum(db_models.ChatHistory.score_total) > user_weekly)
            .all()
        )
        rank = len(higher) + 1

    # Current streak: number of consecutive days with at least one message.
    rows = (
        db.query(sqlfunc.date(db_models.ChatHistory.created_at).label("d"))
        .filter(
            db_models.ChatHistory.user_id == user.id,
            db_models.ChatHistory.is_user == True,  # noqa: E712
            db_models.ChatHistory.created_at
                >= datetime.now(timezone.utc) - timedelta(days=30),
        )
        .distinct()
        .order_by(sqlfunc.date(db_models.ChatHistory.created_at).desc())
        .all()
    )
    streak = 0
    today = datetime.now(timezone.utc).date()
    for i, (d,) in enumerate(rows):
        expected = today - timedelta(days=i)
        if d == expected:
            streak += 1
        else:
            break
    total_messages = int((mem.total_messages if mem else 0) or 0)
    score_total = float((mem.score_total if mem else 0) or 0.0)
    average_score = (score_total / total_messages) if total_messages else 0.0

    # SQLite drops tzinfo on read; normalise to naive UTC before diffing.
    days = 0
    if user.created_at:
        created = user.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - created).days
    return {
        # Frontend-expected shape (UserStats in lib/auth-api.ts)
        "total_messages": total_messages,
        "total_sessions": int(total_sessions),
        "total_score": score_total,
        "average_score": round(average_score, 2),
        "best_score": float(best_score),
        "score_by_mode": score_by_mode,
        "score_by_personality": score_by_personality,
        "recent_topics": recent_topics,
        "rank": rank,
        "rank_period": "weekly" if rank is not None else None,
        "achievements_unlocked": unlocked,
        "achievements_total": achievements_total,
        # Legacy fields kept for any older client / test that still
        # reads them. (See audit pass round-9.)
        "score_total": score_total,
        "mode_counts": mode_counts,
        "personality_counts": personality_counts,
        "current_streak_days": streak,
        "favorite_mode": user.favorite_mode,
        "favorite_personality": user.favorite_personality,
        "days_since_signup": days,
    }


# ----- Favorites -----


@router.put("/me/favorites")
def set_favorites(
    req: _FavoriteReq,
    user: Annotated[db_models.User, Depends(auth.get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Set the user's favorite mode and/or personality. Used by the
    chat UI to pre-select these on a new session.
    """
    if req.favorite_mode is not None:
        from .models import RoastMode
        valid = {m.value for m in RoastMode}
        if req.favorite_mode not in valid:
            raise HTTPException(
                status_code=422, detail=f"Invalid mode. Must be one of: {sorted(valid)}"
            )
        user.favorite_mode = req.favorite_mode
    if req.favorite_personality is not None:
        from .models import Personality
        valid = {p.value for p in Personality}
        if req.favorite_personality not in valid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid personality. Must be one of: {sorted(valid)}",
            )
        user.favorite_personality = req.favorite_personality
    db.commit()
    # Return a full UserOut so the frontend can update its session
    # cache in one place (the previous partial-dict response caused
    # the cache to be overwritten with only two fields and silently
    # break the account page for the rest of the session).
    return _build_user_out(user, db)


# ----- Admin JWT login (alternative to X-Admin-Key header) -----


class _AdminLoginReq(BaseModel):
    email: EmailStr
    password: str


@router.post("/admin/login", response_model=auth_schemas.TokenResponse)
def admin_login(
    req: _AdminLoginReq,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> auth_schemas.TokenResponse:
    """Authenticate as an admin user and return a regular user JWT
    that has `is_admin=True`. This is an alternative to passing
    `X-Admin-Key` for admin operations — the front-end can use it
    to render the admin UI after an admin signs in.

    Constant-time via the same dummy-hash dance as /login.
    """
    _DUMMY = "$2b$12$CwTycUXWue0Thq9StjUM0uJ8Vd1IX0Q8dL1.Jjh1hYpQ3P4lp7mZi"
    user = db.query(db_models.User).filter(
        db_models.User.email == req.email.lower(),
    ).first()
    if user is None:
        auth.verify_password(req.password, _DUMMY)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_admin:
        auth.verify_password(req.password, _DUMMY)
        utils.log_action(
            db, action="admin_login_failed_not_admin",
            actor_ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="Not an admin account")
    if not auth.verify_password(req.password, user.hashed_password):
        utils.log_action(
            db, action="admin_login_failed_wrong_password",
            actor_user_id=user.id,
            actor_ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active or user.deleted_at is not None or user.is_banned:
        raise HTTPException(status_code=403, detail="Account cannot sign in")
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = request.client.host if request.client else None
    db.commit()
    utils.log_action(
        db, action="admin_login_success",
        actor_user_id=user.id,
        actor_ip=user.last_login_ip,
    )
    return auth_schemas.TokenResponse(
        access_token=auth.create_access_token(user.id, user.email, user.token_version),
        refresh_token=auth.create_refresh_token(user.id, user.email, user.token_version),
        expires_in=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
