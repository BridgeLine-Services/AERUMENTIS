"""Aerumentis — Authentication Router."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import get_db, Organization, User
from aerumentis.core.hashing import hash_password, verify_password
from aerumentis.core.logging import get_logger
from aerumentis.core.security import (
    AuthenticatedUser, Permission, UserRole, create_token_pair, decode_token,
    get_current_user, require_permission,
)
from aerumentis.models.schemas import (
    ApiKeyCreateRequest, ApiKeyCreatedResponse, ApiKeyResponse, LoginRequest,
    MessageResponse, RefreshRequest, RegisterRequest, TokenResponse, UserResponse,
)
from aerumentis.services.api_key_service import create_api_key, list_api_keys, revoke_api_key

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = get_logger("aerumentis.api.auth")


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    org_id = None
    if request.organization_name:
        slug = request.organization_name.lower().replace(" ", "-")[:100]
        org = Organization(id=str(uuid.uuid4()), name=request.organization_name, slug=slug,
                           org_type=request.organization_type or "mro")
        db.add(org)
        await db.flush()
        org_id = org.id
    user = User(
        id=str(uuid.uuid4()), email=request.email, full_name=request.full_name,
        hashed_password=hash_password(request.password), role=UserRole.ADMIN.value,
        org_id=org_id, is_active=True,
    )
    db.add(user)
    await db.flush()
    tokens = create_token_pair(user_id=user.id, role=UserRole.ADMIN, org_id=org_id, email=user.email)
    logger.info("user_registered", user_id=user.id, email=user.email)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                         token_type="bearer", expires_in=tokens.expires_in)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    user.last_login = datetime.utcnow()
    await db.flush()
    tokens = create_token_pair(user_id=user.id, role=UserRole(user.role), org_id=user.org_id, email=user.email)
    logger.info("user_login", user_id=user.id, email=user.email)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                         token_type="bearer", expires_in=tokens.expires_in)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest):
    token_data = decode_token(request.refresh_token)
    tokens = create_token_pair(user_id=token_data.sub, role=token_data.role, org_id=token_data.org_id, email=token_data.email)
    return TokenResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                         token_type="bearer", expires_in=tokens.expires_in)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name,
                        role=user.role, org_id=user.org_id, is_active=user.is_active,
                        created_date=user.created_date)


@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: AuthenticatedUser = Depends(get_current_user)):
    logger.info("user_logout", user_id=current_user.user_id)
    return MessageResponse(message="Successfully logged out")


# --- API Key Management ---

@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.API_KEY_MANAGE))])
async def create_user_api_key(
    request: ApiKeyCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    api_key, raw_key = await create_api_key(
        db, user_id=current_user.user_id, name=request.name,
        org_id=current_user.org_id, expires_at=request.expires_at,
    )
    return ApiKeyCreatedResponse(
        id=api_key.id, name=api_key.name, key=raw_key, key_prefix=api_key.key_prefix,
        is_active=api_key.is_active, created_date=api_key.created_date,
        last_used=api_key.last_used, expires_at=api_key.expires_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse],
             dependencies=[Depends(require_permission(Permission.API_KEY_MANAGE))])
async def list_user_api_keys(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    keys = await list_api_keys(db, current_user.user_id)
    return [ApiKeyResponse(id=k.id, name=k.name, key_prefix=k.key_prefix, is_active=k.is_active,
                           created_date=k.created_date, last_used=k.last_used, expires_at=k.expires_at)
            for k in keys]


@router.delete("/api-keys/{key_id}", response_model=MessageResponse,
                dependencies=[Depends(require_permission(Permission.API_KEY_MANAGE))])
async def revoke_user_api_key(
    key_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    success = await revoke_api_key(db, key_id, current_user.user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return MessageResponse(message="API key revoked successfully")
