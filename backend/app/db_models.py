"""SQLAlchemy ORM models for users, subscriptions, and history.

These are database-backed models (vs. `models.py` which holds Pydantic
schemas for API requests/responses).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text, JSON, Enum, Float,
    Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GenderPref(str, enum.Enum):
    male = "male"
    female = "female"
    neutral = "neutral"


class SubStatus(str, enum.Enum):
    active = "active"
    cancelled = "cancelled"
    past_due = "past_due"
    completed = "completed"
    pending = "pending"


class PaymentStatus(str, enum.Enum):
    created = "created"
    authorized = "authorized"
    captured = "captured"
    refunded = "refunded"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    gender_preference: Mapped[GenderPref] = mapped_column(
        Enum(GenderPref), default=GenderPref.neutral
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    free_messages_used: Mapped[int] = mapped_column(Integer, default=0)
    # Incremented to invalidate every outstanding JWT (logout-everywhere,
    # password change, account compromise). Compared with the `ver` claim in
    # each access/refresh token. See backend/app/auth.py.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    # Last successful login timestamp. Updated on POST /auth/login.
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Last successful login IP (best-effort, honouring X-Forwarded-For
    # only when behind a trusted proxy). Helps admins spot anomalies.
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(64))
    # Avatar URL (HTTPS) or data URI. Capped at 2 MB raw to prevent
    # storage abuse; the upload endpoint enforces a hard size limit.
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    # Ban fields. Distinct from `is_active`: a banned user can be
    # reactivated by an admin clearing `is_banned`, but the reason
    # and timestamp are kept for the audit log. `is_active=False` is
    # for soft disable (e.g. password compromise); `is_banned=True`
    # is a permanent-ish moderation action.
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(String(500))
    banned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    banned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Cross-session AI memory. The user can clear it; the AI engine
    # uses it to inject context into roasts.
    favorite_mode: Mapped[Optional[str]] = mapped_column(String(32))
    favorite_personality: Mapped[Optional[str]] = mapped_column(String(32))
    # "Remember previous chats" — most recent N roast topics so the
    # AI can callback to them. Truncated strings, capped at 10 entries.
    recent_topics_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    # Soft-delete: if non-NULL, the account has been deleted. The
    # row is retained for 30 days to allow restoration, then
    # hard-deleted by a background job. All user-facing endpoints
    # MUST filter on `deleted_at.is_(None)`.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    subscriptions: Mapped[List["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_history: Mapped[List["ChatHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    roast_sessions: Mapped[List["RoastSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memory: Mapped[Optional["UserMemory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_plans.id"), index=True
    )
    # The plan the user will be on after the current period ends.
    # Used by the downgrade-scheduled flow. NULL = no scheduled change.
    scheduled_plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscription_plans.id"), nullable=True
    )
    status: Mapped[SubStatus] = mapped_column(Enum(SubStatus), default=SubStatus.pending)
    razorpay_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True
    )
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True
    )
    current_period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    # The plan FKs are: plan_id (current) and scheduled_plan_id (downgrade
    # target). SQLAlchemy can't auto-detect which to follow for the
    # `plan` relationship, so we disambiguate with `foreign_keys`.
    plan: Mapped["SubscriptionPlan"] = relationship(
        foreign_keys=[plan_id]
    )
    scheduled_plan: Mapped[Optional["SubscriptionPlan"]] = relationship(
        foreign_keys=[scheduled_plan_id]
    )
    payments: Mapped[List["Payment"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # A user can have at most one active subscription at a time.
        # Enforced by a partial unique index on PostgreSQL. SQLite has
        # limited partial-index support; the application layer also
        # enforces the invariant in `payment_routes.create_order` and
        # `admin_routes.grant_subscription`. See C1 in the audit.
        Index(
            "uq_subscriptions_user_active",
            "user_id",
            "status",
            unique=True,
            postgresql_where=(status.in_([SubStatus.active.value, SubStatus.past_due.value])),
        ),
        # Index for hot lookups: webhook handler finds the subscription
        # attached to a Razorpay order id in O(log n). See audit #6.
        # (Composite (user_id, status, current_period_end) is the index
        # used by the free-tier and `has_active_subscription` queries.)
        Index("ix_subscriptions_user_status_period_end", "user_id", "status", "current_period_end"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True
    )
    razorpay_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    razorpay_signature: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.created
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription"] = relationship(back_populates="payments")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_user: Mapped[bool] = mapped_column(Boolean, nullable=False)
    roast_response: Mapped[Optional[str]] = mapped_column(Text)
    # `roast_score` is reserved for a future per-message score breakdown.
    # Not currently written. See audit #23.
    roast_score: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    score_total: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="chat_history")

    __table_args__ = (
        # Speeds up the day-grouped history list query.
        Index("ix_chat_history_user_created", "user_id", "created_at"),
    )


class RoastSession(Base):
    """Persisted view of an in-memory `app.models.Session`.

    On a long-running host, `SessionStore` is enough. On a free-tier
    host that spins down (Render, Koyeb), every active session is
    wiped from memory on cold start. We save the full state here so
    authenticated users can resume after a spin-down via the
    `/api/session/{id}/recover` endpoint.

    Anonymous sessions are NOT persisted: we have no way to associate
    them with a stable user and their lifetime is short by design.
    """
    __tablename__ = "roast_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # The 32-hex-char session id (128 bits). We store it as a unique
    # string so the same id always maps to the same row across saves.
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    # Nullable: anonymous sessions never get persisted. On recovery we
    # check that the user_id matches the requesting user before exposing
    # the state, so a leaked session id from one user can't be used to
    # peek at another user's transcript.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Mode and personality as plain strings so the table can be read
    # back without depending on the enum values being present.
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    personality: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    roaster_gender: Mapped[Optional[str]] = mapped_column(String(16))
    # Full denormalized state. We trade read/write simplicity for
    # multiple small tables. The session object is small (<= 50
    # messages, scores are ints + 2 strings), so a single JSON column
    # is fine.
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # ended_at is stored as a unix-epoch float (seconds). Without an
    # explicit type, SQLAlchemy 2.0 falls back to the type from the
    # annotation, which on some dialects (notably SQLite) defaults to
    # Integer and silently truncates the fractional part of time.time().
    # Float is correct for both PG (double precision) and SQLite
    # (REAL).
    ended_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[Optional["User"]] = relationship(back_populates="roast_sessions")

    __table_args__ = (
        # Used by the cleanup task: "ended sessions older than N days".
        Index("ix_roast_sessions_user_ended", "user_id", "ended_at"),
    )


class UserMemory(Base):
    """DB-persisted AI memory for a user. Replaces the in-memory
    `app.session.UserMemory` for cross-restart persistence.

    Stores:
      - Per-mode message counts (powers the "most-used mode" stat)
      - Last 20 chat topic strings (powers "remember previous chats")
      - Per-mode win/loss counters (for the comeback-failure badge)
      - A score_total running tally (for fast leaderboard reads)
    """
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Per-mode message counts. JSON: { "savage": 42, "programmer": 12, ... }
    mode_counts_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Per-personality message counts.
    personality_counts_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # The last 20 chat topics (user-extracted intent strings, capped
    # at 64 chars each). The AI engine peeks at this when picking a
    # callback roast.
    recent_topics_json: Mapped[list] = mapped_column(JSON, default=list)
    # Comeback attempts / failures (for the "best comeback" badge).
    comeback_attempts: Mapped[int] = mapped_column(Integer, default=0)
    comeback_failures: Mapped[int] = mapped_column(Integer, default=0)
    # Running damage total. Mirrors `UserMemory` from `app.session`.
    total_damage: Mapped[float] = mapped_column(Float, default=0.0)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    # Cached score (sum of all per-message scores). Refreshed on every
    # message write, not on read.
    score_total: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="memory")


class EmailToken(Base):
    """Single-use tokens for email verification and password reset.

    One table, discriminated by `purpose`. Tokens are stored hashed
    (sha256) so a DB leak doesn't let an attacker use them. Lifetime:
    24h for verification, 1h for password reset.
    """
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), index=True)  # "verify" | "reset"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_email_tokens_user_purpose", "user_id", "purpose"),
    )


class AuditLog(Base):
    """Append-only log of security-relevant and admin actions.

    The app does not enforce retention — operators should set up a
    downstream job to prune rows older than their compliance window.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    actor_ip: Mapped[Optional[str]] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    # The affected user (for admin actions like "user X banned user Y").
    target_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Free-form details, capped at 2 KB.
    details_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class FeatureFlag(Base):
    """Boolean feature flag, toggled by an admin at runtime.

    Cheap DIY alternative to LaunchDarkly. Cached in-process with a
    60s TTL so a flag flip propagates within a minute without hammering
    the DB.
    """
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    updated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Achievement(Base):
    """Catalog of achievements a user can earn.

    Static rows seeded at startup. `key` is the stable identifier
    used by code (e.g. "first_roast"). `category` and `rarity` are
    display-only metadata for the badges UI.
    """
    __tablename__ = "achievements"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🏅")
    category: Mapped[str] = mapped_column(String(32), default="general")
    rarity: Mapped[str] = mapped_column(String(16), default="common")
    # How many points this achievement is worth (for future leaderboard
    # tiebreakers). Not used in the UI today.
    points: Mapped[int] = mapped_column(Integer, default=10)
    # Sort order in the badges grid.
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class UserAchievement(Base):
    """User-owned achievement unlocks. Unique on (user_id, achievement_key)."""
    __tablename__ = "user_achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    achievement_key: Mapped[str] = mapped_column(
        ForeignKey("achievements.key", ondelete="CASCADE"), index=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_key", name="uq_user_achievement"),
    )


class LeaderboardSnapshot(Base):
    """Periodic snapshot of the leaderboard for cheap reads.

    Populated by a background job (see `app/jobs.py`) every hour.
    Lets the public leaderboard render in O(1) without re-aggregating
    the entire chat_history table on every request.
    """
    __tablename__ = "leaderboard_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)  # "week" | "month" | "all"
    period_id: Mapped[str] = mapped_column(String(16), index=True)  # "2026-W23" | "2026-06" | "all"
    rank: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    total_damage: Mapped[float] = mapped_column(Float, default=0.0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    __table_args__ = (
        Index("ix_snapshot_period_rank", "period", "period_id", "rank"),
    )

