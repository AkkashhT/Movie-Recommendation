from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None

    @validator("password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    onboarding_done: bool


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    role: str
    onboarding_done: bool
    interaction_count: int
    avatar_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class OnboardingRequest(BaseModel):
    genre_ids: list[int] = Field(..., min_length=3, description="At least 3 genres")
    actor_ids: list[int] = Field(..., min_length=2, description="At least 2 actors")
    director_ids: list[int] = Field(..., min_length=1, description="At least 1 director")
