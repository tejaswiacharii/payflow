from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


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