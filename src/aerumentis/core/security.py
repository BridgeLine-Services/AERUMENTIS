"""
Aerumentis — Security & Authentication
JWT auth + API keys + RBAC.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from pydantic import BaseModel

from aerumentis.core.config import get_settings
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.security")
settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    ENGINEER = "engineer"
    MAINTENANCE_TECH = "maintenance_tech"
    GROUND_OPS = "ground_ops"
    VIEWER = "viewer"


class Permission(str, Enum):
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_DELETE = "document:delete"
    DOCUMENT_READ = "document:read"
    RAG_QUERY = "rag:query"
    RAG_ADMIN = "rag:admin"
    KNOWLEDGE_WRITE = "knowledge:write"
    KNOWLEDGE_READ = "knowledge:read"
    OPS_VIEW = "ops:view"
    OPS_MANAGE = "ops:manage"
    USER_MANAGE = "user:manage"
    SYSTEM_ADMIN = "system:admin"


ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.SUPERADMIN: set(Permission),
    UserRole.ADMIN: {
        Permission.DOCUMENT_UPLOAD, Permission.DOCUMENT_DELETE, Permission.DOCUMENT_READ,
        Permission.RAG_QUERY, Permission.RAG_ADMIN,
        Permission.KNOWLEDGE_WRITE, Permission.KNOWLEDGE_READ,
        Permission.OPS_VIEW, Permission.OPS_MANAGE, Permission.USER_MANAGE,
    },
    UserRole.ENGINEER: {
        Permission.DOCUMENT_READ, Permission.RAG_QUERY,
        Permission.KNOWLEDGE_WRITE, Permission.KNOWLEDGE_READ, Permission.OPS_VIEW,
    },
    UserRole.MAINTENANCE_TECH: {
        Permission.DOCUMENT_READ, Permission.RAG_QUERY,
        Permission.KNOWLEDGE_WRITE, Permission.KNOWLEDGE_READ,
    },
    UserRole.GROUND_OPS: {
        Permission.DOCUMENT_READ, Permission.RAG_QUERY,
        Permission.OPS_VIEW, Permission.OPS_MANAGE,
    },
    UserRole.VIEWER: {
        Permission.DOCUMENT_READ, Permission.RAG_QUERY,
        Permission.KNOWLEDGE_READ, Permission.OPS_VIEW,
    },
}


class TokenData(BaseModel):
    sub: str
    org_id: str | None = None
    role: UserRole
    email: str | None = None
    exp: datetime | None = None
    iat: datetime | None = None
    jti: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AuthenticatedUser(BaseModel):
    user_id: str
    role: UserRole
    org_id: str | None = None
    email: str | None = None
    auth_method: str = "jwt"


def create_access_token(
    user_id: str | uuid.UUID,
    role: UserRole,
    org_id: str | None = None,
    email: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": str(user_id), "role": role.value, "exp": expire,
        "iat": datetime.now(timezone.utc), "jti": str(uuid.uuid4()), "type": "access",
    }
    if org_id:
        payload["org_id"] = org_id
    if email:
        payload["email"] = email
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str | uuid.UUID, role: UserRole, org_id: str | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": str(user_id), "role": role.value, "exp": expire,
        "iat": datetime.now(timezone.utc), "jti": str(uuid.uuid4()), "type": "refresh",
    }
    if org_id:
        payload["org_id"] = org_id
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_token_pair(
    user_id: str | uuid.UUID, role: UserRole, org_id: str | None = None, email: str | None = None
) -> TokenPair:
    access = create_access_token(user_id, role, org_id, email)
    refresh = create_refresh_token(user_id, role, org_id)
    return TokenPair(
        access_token=access, refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return TokenData(
            sub=payload["sub"], org_id=payload.get("org_id"),
            role=UserRole(payload["role"]), email=payload.get("email"),
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc) if "iat" in payload else None,
            jti=payload.get("jti"),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("invalid_token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def generate_api_key() -> str:
    raw = secrets.token_urlsafe(32)
    return f"{settings.api_key_prefix}{raw}"


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(permission: Permission):
    def _checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not has_permission(current_user.role, permission):
            logger.warning(
                "permission_denied", user_id=current_user.user_id,
                role=current_user.role.value, permission=permission.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission.value}",
            )
        return current_user
    return _checker


async def get_current_user(
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
) -> AuthenticatedUser:
    if bearer and bearer.credentials:
        token_data = decode_token(bearer.credentials)
        return AuthenticatedUser(
            user_id=token_data.sub, role=token_data.role,
            org_id=token_data.org_id, email=token_data.email, auth_method="jwt",
        )
    if api_key and api_key.startswith(settings.api_key_prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication not yet implemented. Use Bearer token.",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide a Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    api_key: str | None = Security(api_key_header),
) -> AuthenticatedUser | None:
    if not bearer and not api_key:
        return None
    try:
        return await get_current_user(bearer, api_key)
    except HTTPException:
        return None
