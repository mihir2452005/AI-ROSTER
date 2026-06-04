"""Pydantic schemas for authentication and user-related API endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field


# ---- Auth request/response models ----
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)
    gender_preference: Optional[str] = Field(default="neutral", pattern="^(male|female|neutral)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class RefreshRequest(BaseModel):
    refresh_token: str


# ---- User profile ----
class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str]
    gender_preference: str
    is_verified: bool
    is_admin: bool
    free_messages_used: int
    created_at: datetime
    has_active_subscription: bool = False
    # Echoed back so the frontend can detect when its stored token has
    # been invalidated server-side (e.g. after password change or admin
    # deactivation) and force a re-login.
    token_version: int = 0


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    gender_preference: Optional[str] = Field(default=None, pattern="^(male|female|neutral)$")


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---- Subscription plans ----
class PlanOut(BaseModel):
    id: int
    plan_code: str
    name: str
    price_paise: int
    price_display: str
    currency: str
    duration_days: int
    features: dict


class PlanList(BaseModel):
    plans: List[PlanOut]


# ---- Subscriptions ----
class SubscriptionOut(BaseModel):
    id: int
    plan_code: str
    plan_name: str
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    admin_granted: bool
    created_at: datetime


class SubscriptionList(BaseModel):
    subscriptions: List[SubscriptionOut]


# ---- Payments ----
class CreateOrderRequest(BaseModel):
    plan_code: str


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    plan_code: str
    plan_name: str
    key_id: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentOut(BaseModel):
    id: int
    amount: int
    currency: str
    status: str
    description: Optional[str]
    created_at: datetime


# ---- Chat history ----
class ChatHistoryItem(BaseModel):
    id: int
    message: str
    is_user: bool
    roast_response: Optional[str]
    score_total: float
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    items: List[ChatHistoryItem]
    total: int
