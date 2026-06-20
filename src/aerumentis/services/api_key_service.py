"""
Aerumentis — API Key Service
Full CRUD for API keys with secure hashing.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.config import get_settings
from aerumentis.core.database import ApiKey
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.api_keys")
settings = get_settings()


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key_pair() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix). The raw key is only shown once."""
    raw_key = f"{settings.api_key_prefix}{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


async def create_api_key(
    db: AsyncSession, user_id: str, name: str,
    org_id: str | None = None, expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """Create an API key. Returns (api_key_record, raw_key_shown_once)."""
    raw_key, key_hash, key_prefix = generate_api_key_pair()
    api_key = ApiKey(
        key_hash=key_hash, key_prefix=key_prefix, user_id=user_id,
        org_id=org_id, name=name, is_active=True, expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    logger.info("api_key_created", key_id=api_key.id, user_id=user_id, name=name)
    return api_key, raw_key


async def validate_api_key(db: AsyncSession, raw_key: str) -> dict | None:
    """Validate an API key. Returns user info dict if valid, None otherwise."""
    if not raw_key or not raw_key.startswith(settings.api_key_prefix):
        return None

    key_hash = _hash_api_key(raw_key)

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None

    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        logger.warning("api_key_expired", key_id=api_key.id)
        return None

    # Update last_used
    await db.execute(
        update(ApiKey).where(ApiKey.id == api_key.id).values(last_used=datetime.now(timezone.utc))
    )
    await db.flush()

    # Fetch the user
    from aerumentis.core.database import User
    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    # Lazy import to avoid circular dependency
    from aerumentis.core.security import UserRole
    return {
        "user_id": user.id,
        "role": UserRole(user.role),
        "org_id": user.org_id or api_key.org_id,
        "email": user.email,
        "auth_method": "api_key",
    }


async def list_api_keys(db: AsyncSession, user_id: str) -> Sequence[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_date.desc())
    )
    return result.scalars().all()


async def revoke_api_key(db: AsyncSession, key_id: str, user_id: str) -> bool:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        return False
    api_key.is_active = False
    await db.flush()
    logger.info("api_key_revoked", key_id=key_id)
    return True
