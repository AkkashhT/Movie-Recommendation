from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
import hashlib

from app.db.session import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_refresh_token, get_current_user
)
from app.core.config import get_settings
from app.models.user import User, UserPreference, RefreshToken
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserResponse, OnboardingRequest

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    result = await db.execute(select(User).where(
        (User.email == req.email) | (User.username == req.username)
    ))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email or username already taken")

    user = User(
        email=req.email,
        username=req.username,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    await db.flush()  # get user.id

    # Empty preferences row
    pref = UserPreference(user_id=user.id)
    db.add(pref)

    # Tokens
    access = create_access_token(user.id, user.role)
    raw_refresh, refresh_hash = create_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(rt)
    await db.commit()

    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        user_id=user.id,
        role=user.role,
        onboarding_done=user.onboarding_done,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(401, "Account deactivated")

    access = create_access_token(user.id, user.role)
    raw_refresh, refresh_hash = create_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(rt)
    await db.commit()

    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        user_id=user.id,
        role=user.role,
        onboarding_done=user.onboarding_done,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(req.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(401, "Invalid or expired refresh token")

    # Rotate: revoke old, issue new
    rt.revoked = True
    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one()

    access = create_access_token(user.id, user.role)
    raw_refresh, refresh_hash = create_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(new_rt)
    await db.commit()

    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        user_id=user.id,
        role=user.role,
        onboarding_done=user.onboarding_done,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
