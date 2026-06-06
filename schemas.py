"""
schemas.py
----------
All Pydantic models (request bodies + response shapes) in one file
to keep things simple for a single-store deployment.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


# ── Products ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    label:               str
    name:                str
    price:               float
    approx_weight_g:     float | None = None
    image_url:           str   | None = None
    stock_quantity:      int   | None = 0
    low_stock_threshold: int   | None = 10


class ProductOut(BaseModel):
    id:                  int
    label:               str
    name:                str
    price:               float
    approx_weight_g:     float | None
    image_url:           str   | None
    stock_quantity:      int
    low_stock_threshold: int

    class Config:
        from_attributes = True


# ── Training ──────────────────────────────────────────────────────────────────

class TrainingStartRequest(BaseModel):
    label: str          # product label to train (must exist in products table)


class TrainingStatusOut(BaseModel):
    job_id:   str
    status:   str       # queued | running | completed | failed
    progress: int       # 0-100
    accuracy: float | None = None


# ── Model versions ────────────────────────────────────────────────────────────

class ModelVersionOut(BaseModel):
    id:          int
    version:     int
    sha256:      str
    accuracy:    float | None
    approved:    bool
    deployed:    bool
    created_at:  datetime

    class Config:
        from_attributes = True


class ModelLatestOut(BaseModel):
    version:      int
    sha256:       str
    download_url: str


# ── Receipts ──────────────────────────────────────────────────────────────────

class ReceiptItemIn(BaseModel):
    label:    str
    weight_g: float


class ReceiptIn(BaseModel):
    items:          list[dict[str, Any]]
    total:          float
    payment_method: str | None = None


class ReceiptOut(BaseModel):
    id:             int
    items:          list[dict[str, Any]]
    total:          float
    payment_method: str | None
    paid_at:        datetime

    class Config:
        from_attributes = True
