"""
Aerumentis — Database Layer
Async SQLAlchemy 2.0 with PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aerumentis.core.config import get_settings
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.database")
settings = get_settings()

# Build engine kwargs — SQLite (used in tests) doesn't support pool params
_engine_kwargs: dict = {"echo": settings.app_debug and settings.is_development}
if "postgresql" in settings.database_url:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UUIDMixin:
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )


# Import all models so they register with Base.metadata
from aerumentis.models.database_models import (  # noqa: E402, F401
    ApiKey, ChatMessage, ChatSession, Document, Organization, User,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_initialized")


async def close_db() -> None:
    await engine.dispose()
    logger.info("database_closed")
