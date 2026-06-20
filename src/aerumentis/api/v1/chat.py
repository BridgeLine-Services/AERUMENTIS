"""Aerumentis — Chat Router (RAG query endpoint with conversation history)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import get_db
from aerumentis.core.logging import get_logger
from aerumentis.core.security import AuthenticatedUser, Permission, get_current_user, require_permission
from aerumentis.models.schemas import (
    ChatHistoryResponse, ChatMessageResponse, ChatRequest, ChatResponse,
    ChatSessionListResponse, ChatSessionResponse, ChatStreamEvent, CitationResponse,
    MessageResponse, UpdateSessionRequest,
)
from aerumentis.services.chat_history_service import (
    add_message, create_session, delete_session, get_conversation_history,
    get_messages, get_session, list_sessions, update_session_title,
)
from aerumentis.services.rag_engine import get_rag_engine

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger("aerumentis.api.chat")


@router.post("/query", response_model=ChatResponse,
             dependencies=[Depends(require_permission(Permission.RAG_QUERY))])
async def chat_query(
    request: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters: dict = {}
    if request.aircraft_model:
        filters["aircraft_model"] = request.aircraft_model
    if request.manual_type:
        filters["manual_type"] = request.manual_type

    # Handle conversation history — either from session_id or inline
    conversation_history = request.conversation_history or []
    session_id = request.conversation_id

    if session_id:
        session = await get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
        conversation_history = await get_conversation_history(db, session_id, limit=10)
    else:
        # Create a new session for this conversation
        session = await create_session(
            db, user_id=current_user.user_id, org_id=current_user.org_id,
            title=request.question[:80],
        )
        session_id = session.id

    # Save the user's question
    await add_message(db, session_id, "user", request.question)

    rag_engine = get_rag_engine()
    response = await rag_engine.query(
        question=request.question, top_k=request.top_k, score_threshold=request.score_threshold,
        filters=filters if filters else None, conversation_history=conversation_history or None,
    )

    # Save the assistant's response
    await add_message(
        db, session_id, "assistant", response.answer,
        model=response.model, tokens_used=response.tokens_used,
        retrieval_time_ms=response.retrieval_time_ms, generation_time_ms=response.generation_time_ms,
        total_time_ms=response.total_time_ms, context_chunks_used=response.context_chunks_used,
        citations=response.citations,
    )

    logger.info("chat_query", user_id=current_user.user_id, query_length=len(request.question),
                citations_count=len(response.citations), total_time_ms=response.total_time_ms,
                session_id=session_id)

    return ChatResponse(
        answer=response.answer,
        citations=[CitationResponse(chunk_id=c.chunk_id, document_id=c.document_id, filename=c.filename,
                 chunk_index=c.chunk_index, text=c.text, score=c.score, page=c.page, section=c.section)
                   for c in response.citations],
        query=response.query, model=response.model, tokens_used=response.tokens_used,
        retrieval_time_ms=response.retrieval_time_ms, generation_time_ms=response.generation_time_ms,
        total_time_ms=response.total_time_ms, context_chunks_used=response.context_chunks_used,
        conversation_id=session_id,
    )


@router.post("/stream", dependencies=[Depends(require_permission(Permission.RAG_QUERY))])
async def chat_stream(
    request: ChatRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filters: dict = {}
    if request.aircraft_model:
        filters["aircraft_model"] = request.aircraft_model
    if request.manual_type:
        filters["manual_type"] = request.manual_type

    conversation_history = request.conversation_history or []
    session_id = request.conversation_id

    if session_id:
        session = await get_session(db, session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found")
        conversation_history = await get_conversation_history(db, session_id, limit=10)
    else:
        session = await create_session(
            db, user_id=current_user.user_id, org_id=current_user.org_id,
            title=request.question[:80],
        )
        session_id = session.id

    await add_message(db, session_id, "user", request.question)

    rag_engine = get_rag_engine()

    async def event_generator():
        full_response = ""
        citations_data = []
        try:
            async for chunk in rag_engine.query_stream(
                question=request.question, top_k=request.top_k,
                score_threshold=request.score_threshold,
                filters=filters if filters else None,
                conversation_history=conversation_history or None,
            ):
                if chunk.citations is not None and not chunk.content:
                    citations_data = chunk.citations
                    event = ChatStreamEvent(type="citation", conversation_id=session_id, citations=[
                        CitationResponse(chunk_id=c.chunk_id, document_id=c.document_id, filename=c.filename,
                        chunk_index=c.chunk_index, text=c.text, score=c.score, page=c.page, section=c.section)
                        for c in chunk.citations])
                    yield f"data: {event.model_dump_json()}\n\n"
                elif chunk.content:
                    full_response += chunk.content
                    event = ChatStreamEvent(type="content", content=chunk.content, conversation_id=session_id)
                    yield f"data: {event.model_dump_json()}\n\n"
                elif chunk.done:
                    # Save the full response to DB
                    await add_message(db, session_id, "assistant", full_response, citations=citations_data)
                    event = ChatStreamEvent(type="done", conversation_id=session_id)
                    yield f"data: {event.model_dump_json()}\n\n"
        except Exception as e:
            logger.error("stream_error", error=str(e))
            event = ChatStreamEvent(type="error", error=str(e), conversation_id=session_id)
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# --- Conversation History Endpoints ---

@router.get("/sessions", response_model=ChatSessionListResponse,
             dependencies=[Depends(require_permission(Permission.CHAT_HISTORY))])
async def list_chat_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions, total = await list_sessions(db, current_user.user_id, limit=limit, offset=offset)
    return ChatSessionListResponse(
        sessions=[ChatSessionResponse(id=s.id, title=s.title, message_count=s.message_count,
                 is_active=s.is_active, created_date=s.created_date, updated_date=s.updated_date)
                  for s in sessions],
        total=total, limit=limit, offset=offset,
    )


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse,
             dependencies=[Depends(require_permission(Permission.CHAT_HISTORY))])
async def get_chat_history(session_id: str, db: AsyncSession = Depends(get_db)):
    import json
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    messages = await get_messages(db, session_id)
    message_responses = []
    for m in messages:
        citations = []
        if m.citations_json:
            try:
                raw_citations = json.loads(m.citations_json)
                citations = [CitationResponse(**c) for c in raw_citations]
            except Exception:
                pass
        message_responses.append(ChatMessageResponse(
            id=m.id, role=m.role, content=m.content, model=m.model,
            tokens_used=m.tokens_used, total_time_ms=m.total_time_ms,
            context_chunks_used=m.context_chunks_used, citations=citations,
            created_date=m.created_date,
        ))
    return ChatHistoryResponse(
        session=ChatSessionResponse(id=session.id, title=session.title,
            message_count=session.message_count, is_active=session.is_active,
            created_date=session.created_date, updated_date=session.updated_date),
        messages=message_responses,
    )


@router.patch("/sessions/{session_id}", response_model=MessageResponse,
               dependencies=[Depends(require_permission(Permission.CHAT_HISTORY))])
async def update_session_title_endpoint(
    session_id: str, request: UpdateSessionRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    success = await update_session_title(db, session_id, request.title, current_user.user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return MessageResponse(message="Session title updated")


@router.delete("/sessions/{session_id}", response_model=MessageResponse,
                dependencies=[Depends(require_permission(Permission.CHAT_HISTORY))])
async def delete_chat_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    success = await delete_session(db, session_id, current_user.user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return MessageResponse(message="Session deleted successfully")
