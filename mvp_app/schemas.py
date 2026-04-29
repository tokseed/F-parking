from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    telegram_id: str | None = None
    name: str
    home_area: str


class UserRead(BaseModel):
    id: int
    telegram_id: str | None
    name: str
    role: str
    home_area: str
    created_at: datetime


class SpotCreate(BaseModel):
    user_id: int
    area: str
    address: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    confidence: int = Field(default=50, ge=0, le=100)
    ttl_minutes: int = Field(default=10, ge=1, le=120)


class SpotUpdateStatus(BaseModel):
    status: str


class SpotRead(BaseModel):
    id: int
    user_id: int
    area: str
    address: str
    latitude: float
    longitude: float
    status: str
    confidence: int
    expires_at: datetime
    created_at: datetime


class SubscriptionCreate(BaseModel):
    user_id: int
    plan: str
    amount_rub: int
    duration_days: int = Field(default=1, ge=1, le=30)


class SubscriptionRead(BaseModel):
    id: int
    user_id: int
    plan: str
    status: str
    starts_at: datetime
    ends_at: datetime
    amount_rub: int
    created_at: datetime


class ReportCreate(BaseModel):
    spot_id: int
    user_id: int
    reason: str


class ReportRead(BaseModel):
    id: int
    spot_id: int
    user_id: int
    reason: str
    status: str
    created_at: datetime
