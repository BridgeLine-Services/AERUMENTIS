"""Aerumentis — Chat Router (RAG query endpoint)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from aerumentis.core.logging import get_logger
from aerumentis.core.security import AuthenticatedUser, Permission, get_current_user, require_permission
from aerumentis.models.schemas import ChatRequest, ChatResponse, ChatStreamEvent, CitationResponse
from aerumentis.services.rag_engine import get_rag_engine

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger("aerumentis.api.chat")


@router.post("/query", response_model=ChatResponse,
             dependencies=[Depends(require_permission(Permission.RAG_QUERY))])
async def chat_query(request: ChatRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    filters: dict = {}
    if request.aircraft_model: filters["aircraft_model"] = request.aircraft_model
    if request.manual_type: filters["manual_type"] = request.manual_type
    rag_engine = get_rag_engine()
    response = await rag_engine.query(
        question=request.question, top_k=request.top_k, score_threshold=request.score_threshold,
        filters=filters if filters else None, conversation_history=request.conversation_history or None,
    )
    logger.info("chat_query", user_id=current_user.user_id, query_length=len(request.question),
                citations_count=len(response.citations), total_time_ms=response.total_time_ms)
    return ChatResponse(
        answer=response.answer,
        citations=[CitationResponse(chunk_id=c.chunk_id, document_id=c.document_id, filename=c.filename,
                 chunk_index=c.chunk_index, text=c.text, score=c.score, page=c.page, section=c.section)
                   for c in response.citations],
        query=response.query, model=response.model, tokens_used=response.tokens_used,
        retrieval_time_ms=response.retrieval_time_ms, generation_time_ms=response.generation_time_ms,
        total_time_ms=response.total_time_ms, context_chunks_used=response.context_chunks_used,
    )


@router.post("/stream", dependencies=[Depends(require_permission(Permission.RAG_QUERY))])
async def chat_stream(request: ChatRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    filters: dict = {}
    if request.aircraft_model: filters["aircraft_model"] = request.aircraft_model
    if request.manual_type: filters["manual_type"] = request.manual_type
    rag_engine = get_rag_engine()

    async def event_generator():
        try:
            async for chunk in rag_engine.query_stream(
                question=request.question, top_k=request.top_k, score_threshold=request.score_threshold,
                filters=filters if filters else None, conversation_history=request.conversation_history or None,
            ):
                if chunk.citations is not None and not chunk.content:
                    event = ChatStreamEvent(type="citation", citations=[
                        CitationResponse(chunk_id=c.chunk_id, document_id=c.document_id, filename=c.filename,
                        chunk_index=c.chunk_index, text=c.text, score=c.score, page=c.page, section=c.section)
                        for c in chunk.citations])
                    yield f"data: {event.model_dump_json()}\n\n"
                elif chunk.content:
                    event = ChatStreamEvent(type="content", content=chunk.content)
                    yield f"data: {event.model_dump_json()}\n\n"
                elif chunk.done:
                    event = ChatStreamEvent(type="done")
                    yield f"data: {event.model_dump_json()}\n\n"
        except Exception as e:
            logger.error("stream_error", error=str(e))
            event = ChatStreamEvent(type="error", error=str(e))
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})
