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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

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
        cascade="all, delete-orphan"
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
    plan: Mapped["SubscriptionPlan"] = relationship()
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
    ended_at: Mapped[Optional[float]] = mapped_column()  # unix seconds
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[Optional["User"]] = relationship(overlaps="roast_sessions")

    __table_args__ = (
        # Used by the cleanup task: "ended sessions older than N days".
        Index("ix_roast_sessions_user_ended", "user_id", "ended_at"),
    )

