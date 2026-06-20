"""
Aerumentis — Database Models
SQLAlchemy 2.0 models for document metadata, chat history, and API keys.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, Integer, Float, Boolean, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aerumentis.core.database import Base, TimestampMixin, UUIDMixin


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    org_type: Mapped[str] = mapped_column(String(50), nullable=False, default="mro")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    users: Mapped[list[User]] = relationship(back_populates="organization", foreign_keys="User.org_id")


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization | None] = relationship(
        back_populates="users", foreign_keys=[org_id]
    )
    api_keys: Mapped[list[ApiKey]] = relationship(back_populates="user", foreign_keys="ApiKey.user_id")


class ApiKey(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys", foreign_keys=[user_id])


class Document(UUIDMixin, TimestampMixin, Base):
    """Metadata for ingested maintenance documents."""
    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active, processing, failed, deleted
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata fields
    aircraft_model: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    manual_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    manual_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated

    # Ownership
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("ix_documents_org_aircraft", "org_id", "aircraft_model"),
        Index("ix_documents_org_manual_type", "org_id", "manual_type"),
    )


class ChatSession(UUIDMixin, TimestampMixin, Base):
    """A conversation session for chat history."""
    __tablename__ = "chat_sessions"

    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled Conversation")
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", foreign_keys="ChatMessage.session_id",
        order_by="ChatMessage.created_date", cascade="all, delete-orphan"
    )


class ChatMessage(UUIDMixin, TimestampMixin, Base):
    """Individual messages within a chat session."""
    __tablename__ = "chat_messages"

    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieval_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    generation_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    context_chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-serialized citations

    session: Mapped[ChatSession] = relationship(back_populates="messages", foreign_keys=[session_id])

    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_date"),
    )
