"""
Aerumentis — Maintenance Module Router
Phase 1 maintenance-specific endpoints: troubleshooting suggestions, manual section lookup.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from aerumentis.core.logging import get_logger
from aerumentis.core.security import AuthenticatedUser, Permission, get_current_user, require_permission
from aerumentis.models.schemas import ChatResponse, CitationResponse
from aerumentis.services.rag_engine import get_rag_engine

router = APIRouter(prefix="/maintenance", tags=["maintenance"])
logger = get_logger("aerumentis.api.maintenance")


class TroubleshootingRequest(BaseModel):
    symptom: str = Field(..., min_length=3, max_length=1000, description="The symptom or issue being observed")
    aircraft_model: str | None = Field(None, description="e.g. '737 NG', 'A320'")
    system: str | None = Field(None, description="e.g. 'hydraulic', 'electrical', 'fuel'")
    top_k: int | None = Field(None, ge=1, le=20)


class TroubleshootingResponse(BaseModel):
    question: str
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    model: str = ""
    tokens_used: int = 0
    total_time_ms: float = 0.0


@router.post("/troubleshoot", response_model=TroubleshootingResponse,
             dependencies=[Depends(require_permission(Permission.RAG_QUERY))])
async def troubleshoot(
    request: TroubleshootingRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Get AI-powered troubleshooting suggestions based on observed symptoms."""
    question = f"Troubleshooting: {request.symptom}"
    if request.system:
        question += f" — System: {request.system}"
    if request.aircraft_model:
        question += f" — Aircraft: {request.aircraft_model}"

    filters: dict = {}
    if request.aircraft_model:
        filters["aircraft_model"] = request.aircraft_model

    rag_engine = get_rag_engine()
    response = await rag_engine.query(
        question=question, top_k=request.top_k or 8,
        score_threshold=0.60,  # Lower threshold for troubleshooting to get more context
        filters=filters if filters else None,
    )

    logger.info("troubleshoot_query", user_id=current_user.user_id,
                symptom=request.symptom[:80], citations=len(response.citations))

    return TroubleshootingResponse(
        question=question, answer=response.answer,
        citations=[CitationResponse(chunk_id=c.chunk_id, document_id=c.document_id, filename=c.filename,
                 chunk_index=c.chunk_index, text=c.text, score=c.score, page=c.page, section=c.section)
                   for c in response.citations],
        model=response.model, tokens_used=response.tokens_used,
        total_time_ms=response.total_time_ms,
    )


@router.get("/search", dependencies=[Depends(require_permission(Permission.DOCUMENT_READ))])
async def search_manuals(
    q: str = Query(..., min_length=3, max_length=500, description="Search query"),
    aircraft_model: str | None = Query(None),
    manual_type: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Search maintenance manuals without LLM generation — returns relevant chunks directly."""
    from aerumentis.services.embedding_service import get_embedding_service
    from aerumentis.services.vector_store import get_vector_store

    embedding_service = get_embedding_service()
    vector_store = get_vector_store()

    query_vector = await embedding_service.embed(q)
    filters: dict = {}
    if aircraft_model:
        filters["aircraft_model"] = aircraft_model
    if manual_type:
        filters["manual_type"] = manual_type

    results = await vector_store.search(
        collection_name="maintenance_docs", query_vector=query_vector,
        top_k=top_k, score_threshold=0.50, filters=filters if filters else None,
    )

    return {
        "query": q,
        "results": [
            {
                "chunk_id": r.id, "score": r.score,
                "filename": r.payload.get("filename", ""),
                "chunk_index": r.payload.get("chunk_index", 0),
                "text": r.payload.get("text", "")[:1000],
                "aircraft_model": r.payload.get("aircraft_model"),
                "manual_type": r.payload.get("manual_type"),
            }
            for r in results
        ],
        "total": len(results),
    }
