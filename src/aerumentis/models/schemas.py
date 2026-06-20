"""Aerumentis — API Response Schemas (Pydantic models)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    environment: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: dict[str, str] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    organization_name: str | None = None
    organization_type: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    org_id: str | None = None
    is_active: bool
    created_date: datetime


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    created_date: datetime
    last_used: datetime | None = None
    expires_at: datetime | None = None


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str  # Only shown once on creation


class IngestionResponse(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    total_tokens: int
    checksum: str
    status: str
    error: str | None = None
    message: str = ""


class DocumentMetadataResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    chunk_count: int
    total_tokens: int
    status: str
    aircraft_model: str | None = None
    manual_type: str | None = None
    manual_number: str | None = None
    revision: str | None = None
    effective_date: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_date: datetime
    updated_date: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentMetadataResponse]
    total: int
    limit: int
    offset: int


class DocumentStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_tokens: int
    by_aircraft_model: dict[str, int] = Field(default_factory=dict)
    by_manual_type: dict[str, int] = Field(default_factory=dict)


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    score: float
    page: int | None = None
    section: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int | None = Field(None, ge=1, le=20)
    score_threshold: float | None = Field(None, ge=0.0, le=1.0)
    aircraft_model: str | None = None
    manual_type: str | None = None
    conversation_id: str | None = None
    conversation_history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    query: str
    model: str
    tokens_used: int
    retrieval_time_ms: float
    generation_time_ms: float
    total_time_ms: float
    context_chunks_used: int
    conversation_id: str | None = None


class ChatStreamEvent(BaseModel):
    type: str
    content: str = ""
    citations: list[CitationResponse] = Field(default_factory=list)
    conversation_id: str | None = None
    error: str | None = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    message_count: int
    is_active: bool
    created_date: datetime
    updated_date: datetime


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionResponse]
    total: int
    limit: int
    offset: int


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    model: str | None = None
    tokens_used: int
    total_time_ms: float
    context_chunks_used: int
    citations: list[CitationResponse] = Field(default_factory=list)
    created_date: datetime


class ChatHistoryResponse(BaseModel):
    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class UpdateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class KnowledgeEntryCreate(BaseModel):
    title: str
    content: str
    aircraft_model: str | None = None
    system_affected: str | None = None
    tags: list[str] = Field(default_factory=list)


class KnowledgeEntryResponse(BaseModel):
    id: str
    title: str
    content: str
    aircraft_model: str | None = None
    system_affected: str | None = None
    tags: list[str]
    created_date: datetime
    updated_date: datetime


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int
