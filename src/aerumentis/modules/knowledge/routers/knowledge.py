"""Aerumentis — Knowledge Module (Phase 2 Stub)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from aerumentis.core.logging import get_logger
from aerumentis.core.security import Permission, require_permission
from aerumentis.models.schemas import KnowledgeEntryCreate, KnowledgeEntryResponse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = get_logger("aerumentis.modules.knowledge")


@router.post("/entries", response_model=KnowledgeEntryResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def create_knowledge_entry(entry: KnowledgeEntryCreate):
    logger.info("knowledge_entry_created_stub", title=entry.title)
    return KnowledgeEntryResponse(id="stub-knowledge-id", title=entry.title, content=entry.content,
        aircraft_model=entry.aircraft_model, system_affected=entry.system_affected,
        tags=entry.tags, created_date=datetime.utcnow(), updated_date=datetime.utcnow())


@router.get("/entries", dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def list_knowledge_entries(limit: int = 20, offset: int = 0):
    return {"entries": [], "total": 0, "limit": limit, "offset": offset,
            "message": "Knowledge module is in Phase 2 development."}


@router.post("/search", dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def search_knowledge(query: str):
    return {"query": query, "results": [], "total_matches": 0,
            "message": "Knowledge search is in Phase 2 development."}


@router.post("/interviews", dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def create_voice_interview(technician_name: str, topic: str):
    return {"interview_id": "stub-interview-id", "technician_name": technician_name,
            "topic": topic, "status": "pending_transcription",
            "message": "Voice interview ingestion is in Phase 2 development."}
