"""
Aerumentis — Chat History Service
Persist and retrieve conversation sessions and messages.
"""
from __future__ import annotations

import json
from typing import Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import ChatMessage, ChatSession
from aerumentis.core.logging import get_logger
from aerumentis.services.rag_engine import Citation

logger = get_logger("aerumentis.chat_history")


async def create_session(
    db: AsyncSession, user_id: str | None = None,
    org_id: str | None = None, title: str = "Untitled Conversation",
) -> ChatSession:
    session = ChatSession(title=title, user_id=user_id, org_id=org_id, is_active=True)
    db.add(session)
    await db.flush()
    logger.info("chat_session_created", session_id=session.id, user_id=user_id)
    return session


async def get_session(db: AsyncSession, session_id: str) -> ChatSession | None:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()


async def list_sessions(
    db: AsyncSession, user_id: str, limit: int = 20, offset: int = 0
) -> tuple[Sequence[ChatSession], int]:
    count_result = await db.execute(
        select(func.count(ChatSession.id)).where(
            ChatSession.user_id == user_id, ChatSession.is_active == True  # noqa: E712
        )
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.is_active == True)  # noqa: E712
        .order_by(ChatSession.updated_date.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all(), total


async def add_message(
    db: AsyncSession, session_id: str, role: str, content: str,
    model: str | None = None, tokens_used: int = 0,
    retrieval_time_ms: float = 0.0, generation_time_ms: float = 0.0,
    total_time_ms: float = 0.0, context_chunks_used: int = 0,
    citations: list[Citation] | None = None,
) -> ChatMessage:
    citations_json = json.dumps([c.__dict__ for c in citations]) if citations else None
    message = ChatMessage(
        session_id=session_id, role=role, content=content, model=model,
        tokens_used=tokens_used, retrieval_time_ms=retrieval_time_ms,
        generation_time_ms=generation_time_ms, total_time_ms=total_time_ms,
        context_chunks_used=context_chunks_used, citations_json=citations_json,
    )
    db.add(message)
    await db.flush()

    # Update session message count
    await db.execute(
        update(ChatSession).where(ChatSession.id == session_id)
        .values(message_count=ChatSession.message_count + 1)
    )
    await db.flush()
    return message


async def get_messages(db: AsyncSession, session_id: str, limit: int = 50) -> Sequence[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_date.asc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_conversation_history(db: AsyncSession, session_id: str, limit: int = 10) -> list[dict[str, str]]:
    """Get conversation history formatted for the RAG engine."""
    messages = await get_messages(db, session_id, limit=limit)
    history: list[dict[str, str]] = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            history.append({"role": msg.role, "content": msg.content})
    return history


async def delete_session(db: AsyncSession, session_id: str, user_id: str) -> bool:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return False
    session.is_active = False
    await db.flush()
    logger.info("chat_session_deleted", session_id=session_id)
    return True


async def update_session_title(db: AsyncSession, session_id: str, title: str, user_id: str) -> bool:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return False
    session.title = title
    await db.flush()
    return True
