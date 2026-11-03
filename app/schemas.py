from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal

class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt only uses the first 72 bytes, so cap the length
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class WalletOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    balance: Decimal
    currency: str
    created_at: datetime

class TransferCreate(BaseModel):
    receiver_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    receiver_id: int
    amount: Decimal
    currency: str
    status: str
    idempotency_key: str
    created_at: datetime

class TransactionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: Literal["sent", "received"]
    sender_id: int
    receiver_id: int
    amount: Decimal
    currency: str
    status: str
    created_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionHistoryItem]
    page: int
    page_size: int
    total: int


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    is_read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    page: int
    page_size: int
    total: int