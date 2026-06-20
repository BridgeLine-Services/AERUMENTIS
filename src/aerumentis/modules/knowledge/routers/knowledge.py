"""
Aerumentis — Knowledge Module Router (Phase 2)
Full implementation: knowledge entries, repair history, voice interviews, pattern matching, knowledge graph.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import get_db
from aerumentis.core.logging import get_logger
from aerumentis.core.security import AuthenticatedUser, Permission, get_current_user, require_permission
from aerumentis.models.schemas import MessageResponse
from aerumentis.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = get_logger("aerumentis.api.knowledge")


# ─── Schemas ───

from pydantic import BaseModel, Field


class KnowledgeEntryCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    content: str = Field(..., min_length=10)
    entry_type: str = Field("technician_note", pattern="^(technician_note|repair_history|incident_report|troubleshooting_tip|best_practice|safety_advisory)$")
    aircraft_model: str | None = None
    system_affected: str | None = None
    component_affected: str | None = None
    ata_chapter: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence_score: float = Field(0.5, ge=0.0, le=1.0)


class KnowledgeEntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    aircraft_model: str | None = None
    system_affected: str | None = None
    component_affected: str | None = None
    ata_chapter: str | None = None
    tags: list[str] | None = None
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)


class KnowledgeEntryResponse(BaseModel):
    id: str
    title: str
    content: str
    entry_type: str
    aircraft_model: str | None = None
    system_affected: str | None = None
    component_affected: str | None = None
    ata_chapter: str | None = None
    tags: list[str] = Field(default_factory=list)
    author_name: str | None = None
    status: str
    confidence_score: float
    verified: bool
    verified_by: str | None = None
    chunk_count: int
    from_interview: bool
    interview_id: str | None = None
    created_date: datetime
    updated_date: datetime


class KnowledgeListResponse(BaseModel):
    entries: list[KnowledgeEntryResponse]
    total: int
    limit: int
    offset: int


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(10, ge=1, le=50)
    score_threshold: float = Field(0.55, ge=0.0, le=1.0)
    aircraft_model: str | None = None
    entry_type: str | None = None
    verified_only: bool = False


class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    score: float
    entry_id: str
    title: str
    text: str
    entry_type: str
    aircraft_model: str | None = None
    system_affected: str | None = None
    ata_chapter: str | None = None
    author_name: str | None = None
    confidence_score: float
    verified: bool


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeSearchResult]
    total: int


class PatternMatchRequest(BaseModel):
    symptom: str = Field(..., min_length=3, max_length=1000, description="The symptom or issue to search for")
    aircraft_model: str | None = None
    system_affected: str | None = None
    top_k: int = Field(15, ge=1, le=50)


class PatternMatchCause(BaseModel):
    cause: str
    occurrences: int


class PatternMatchResolution(BaseModel):
    resolution: str
    occurrences: int


class PatternMatchRelatedEntry(BaseModel):
    entry_id: str
    title: str
    score: float
    entry_type: str
    text: str
    aircraft_model: str | None = None
    verified: bool


class PatternMatchRelatedRepair(BaseModel):
    id: str
    aircraft_tail: str | None = None
    symptom: str
    diagnosis: str
    resolution: str
    recurrence: str
    severity: str
    technician_name: str | None = None
    created_date: str


class PatternMatchResponse(BaseModel):
    query: str
    total_occurrences: int
    knowledge_base_matches: int
    repair_history_matches: int
    most_common_causes: list[PatternMatchCause]
    most_common_resolutions: list[PatternMatchResolution]
    related_entries: list[PatternMatchRelatedEntry]
    related_repairs: list[PatternMatchRelatedRepair]
    summary: str


class RepairHistoryCreate(BaseModel):
    aircraft_tail_number: str | None = None
    aircraft_model: str | None = None
    system_affected: str | None = None
    component_affected: str | None = None
    ata_chapter: str | None = None
    symptom: str = Field(..., min_length=3)
    diagnosis: str = Field(..., min_length=3)
    resolution: str = Field(..., min_length=3)
    parts_replaced: str | None = None
    labor_hours: float | None = Field(None, ge=0)
    downtime_hours: float | None = Field(None, ge=0)
    recurrence: str = Field("first_occurrence", pattern="^(first_occurrence|recurring|chronic)$")
    severity: str = Field("minor", pattern="^(minor|moderate|major|critical)$")
    technician_name: str | None = None


class RepairHistoryResponse(BaseModel):
    id: str
    aircraft_tail_number: str | None = None
    aircraft_model: str | None = None
    system_affected: str | None = None
    component_affected: str | None = None
    ata_chapter: str | None = None
    symptom: str
    diagnosis: str
    resolution: str
    parts_replaced: str | None = None
    labor_hours: float | None = None
    downtime_hours: float | None = None
    recurrence: str
    severity: str
    technician_name: str | None = None
    pattern_match_count: int
    knowledge_entry_id: str | None = None
    created_date: datetime


class RepairHistoryListResponse(BaseModel):
    repairs: list[RepairHistoryResponse]
    total: int
    limit: int
    offset: int


class VoiceInterviewCreate(BaseModel):
    technician_name: str = Field(..., min_length=1, max_length=255)
    technician_role: str | None = None
    years_experience: int | None = Field(None, ge=0, le=70)
    topic: str = Field(..., min_length=3, max_length=500)
    aircraft_model: str | None = None
    system_affected: str | None = None


class VoiceInterviewResponse(BaseModel):
    id: str
    technician_name: str
    technician_role: str | None = None
    years_experience: int | None = None
    topic: str
    aircraft_model: str | None = None
    system_affected: str | None = None
    audio_duration_sec: float
    audio_format: str | None = None
    transcript: str | None = None
    transcript_word_count: int
    status: str
    processing_error: str | None = None
    entries_created: int
    created_date: datetime
    updated_date: datetime


class VoiceInterviewListResponse(BaseModel):
    interviews: list[VoiceInterviewResponse]
    total: int
    limit: int
    offset: int


class TranscriptUpdate(BaseModel):
    transcript: str = Field(..., min_length=10)
    duration_sec: float = Field(0.0, ge=0)
    language: str = "en"


class KnowledgeStatsResponse(BaseModel):
    total_entries: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_aircraft_model: dict[str, int] = Field(default_factory=dict)
    by_system: dict[str, int] = Field(default_factory=dict)
    verified_entries: int
    from_interviews: int
    total_repairs: int
    recurring_issues: int
    chronic_issues: int
    total_interviews: int
    completed_interviews: int
    total_interview_word_count: int


class KnowledgeGraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


# ─── Helper ───

def _entry_to_response(e) -> KnowledgeEntryResponse:
    return KnowledgeEntryResponse(
        id=e.id, title=e.title, content=e.content, entry_type=e.entry_type,
        aircraft_model=e.aircraft_model, system_affected=e.system_affected,
        component_affected=e.component_affected, ata_chapter=e.ata_chapter,
        tags=e.tags.split(",") if e.tags else [],
        author_name=e.author_name, status=e.status,
        confidence_score=e.confidence_score, verified=e.verified,
        verified_by=e.verified_by, chunk_count=e.chunk_count,
        from_interview=bool(e.interview_id), interview_id=e.interview_id,
        created_date=e.created_date, updated_date=e.updated_date,
    )


def _repair_to_response(r) -> RepairHistoryResponse:
    return RepairHistoryResponse(
        id=r.id, aircraft_tail_number=r.aircraft_tail_number,
        aircraft_model=r.aircraft_model, system_affected=r.system_affected,
        component_affected=r.component_affected, ata_chapter=r.ata_chapter,
        symptom=r.symptom, diagnosis=r.diagnosis, resolution=r.resolution,
        parts_replaced=r.parts_replaced, labor_hours=r.labor_hours,
        downtime_hours=r.downtime_hours, recurrence=r.recurrence,
        severity=r.severity, technician_name=r.technician_name,
        pattern_match_count=r.pattern_match_count,
        knowledge_entry_id=r.knowledge_entry_id, created_date=r.created_date,
    )


def _interview_to_response(i) -> VoiceInterviewResponse:
    return VoiceInterviewResponse(
        id=i.id, technician_name=i.technician_name, technician_role=i.technician_role,
        years_experience=i.years_experience, topic=i.topic,
        aircraft_model=i.aircraft_model, system_affected=i.system_affected,
        audio_duration_sec=i.audio_duration_sec, audio_format=i.audio_format,
        transcript=i.transcript, transcript_word_count=i.transcript_word_count,
        status=i.status, processing_error=i.processing_error,
        entries_created=i.entries_created,
        created_date=i.created_date, updated_date=i.updated_date,
    )


# ─── Knowledge Entry Endpoints ───

@router.post("/entries", response_model=KnowledgeEntryResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def create_entry(
    request: KnowledgeEntryCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await knowledge_service.create_knowledge_entry(
        db=db, title=request.title, content=request.content,
        entry_type=request.entry_type, aircraft_model=request.aircraft_model,
        system_affected=request.system_affected, component_affected=request.component_affected,
        ata_chapter=request.ata_chapter, tags=request.tags,
        author_id=current_user.user_id, author_name=current_user.email,
        org_id=current_user.org_id, confidence_score=request.confidence_score,
    )
    return _entry_to_response(entry)


@router.get("/entries", response_model=KnowledgeListResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def list_entries(
    entry_type: str | None = Query(None),
    aircraft_model: str | None = Query(None),
    system_affected: str | None = Query(None),
    ata_chapter: str | None = Query(None),
    verified: bool | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entries, total = await knowledge_service.list_knowledge_entries(
        db, org_id=current_user.org_id, limit=limit, offset=offset,
        entry_type=entry_type, aircraft_model=aircraft_model,
        system_affected=system_affected, ata_chapter=ata_chapter, verified=verified,
    )
    return KnowledgeListResponse(
        entries=[_entry_to_response(e) for e in entries],
        total=total, limit=limit, offset=offset,
    )


@router.get("/entries/{entry_id}", response_model=KnowledgeEntryResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def get_entry(entry_id: str, db: AsyncSession = Depends(get_db)):
    entry = await knowledge_service.get_knowledge_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge entry not found")
    return _entry_to_response(entry)


@router.patch("/entries/{entry_id}", response_model=KnowledgeEntryResponse,
              dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def update_entry(
    entry_id: str, request: KnowledgeEntryUpdate, db: AsyncSession = Depends(get_db),
):
    updates = request.model_dump(exclude_none=True)
    entry = await knowledge_service.update_knowledge_entry(db, entry_id, updates)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge entry not found")
    return _entry_to_response(entry)


@router.post("/entries/{entry_id}/verify", response_model=KnowledgeEntryResponse,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def verify_entry(
    entry_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await knowledge_service.verify_knowledge_entry(db, entry_id, current_user.user_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge entry not found")
    return _entry_to_response(entry)


@router.delete("/entries/{entry_id}", response_model=MessageResponse,
               dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def delete_entry(entry_id: str, db: AsyncSession = Depends(get_db)):
    success = await knowledge_service.delete_knowledge_entry(db, entry_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge entry not found")
    return MessageResponse(message="Knowledge entry archived successfully")


# ─── Search ───

@router.post("/search", response_model=KnowledgeSearchResponse,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def search(
    request: KnowledgeSearchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results = await knowledge_service.search_knowledge(
        db, request.query, org_id=current_user.org_id,
        top_k=request.top_k, score_threshold=request.score_threshold,
        aircraft_model=request.aircraft_model, entry_type=request.entry_type,
        verified_only=request.verified_only,
    )
    return KnowledgeSearchResponse(
        query=request.query,
        results=[KnowledgeSearchResult(**r) for r in results],
        total=len(results),
    )


# ─── Pattern Matching ───

@router.post("/patterns", response_model=PatternMatchResponse,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def find_patterns(
    request: PatternMatchRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The killer feature: 'Have we seen this before?'"""
    result = await knowledge_service.find_similar_issues(
        db, request.symptom, org_id=current_user.org_id,
        aircraft_model=request.aircraft_model, system_affected=request.system_affected,
        top_k=request.top_k,
    )
    return PatternMatchResponse(**result)


# ─── Repair History ───

@router.post("/repairs", response_model=RepairHistoryResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def create_repair(
    request: RepairHistoryCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repair = await knowledge_service.create_repair_history(
        db=db, aircraft_tail_number=request.aircraft_tail_number,
        aircraft_model=request.aircraft_model, system_affected=request.system_affected,
        component_affected=request.component_affected, ata_chapter=request.ata_chapter,
        symptom=request.symptom, diagnosis=request.diagnosis, resolution=request.resolution,
        parts_replaced=request.parts_replaced, labor_hours=request.labor_hours,
        downtime_hours=request.downtime_hours, recurrence=request.recurrence,
        severity=request.severity, technician_id=current_user.user_id,
        technician_name=request.technician_name, org_id=current_user.org_id,
    )
    return _repair_to_response(repair)


@router.get("/repairs", response_model=RepairHistoryListResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def list_repairs(
    aircraft_model: str | None = Query(None),
    system_affected: str | None = Query(None),
    recurrence: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repairs, total = await knowledge_service.list_repair_history(
        db, org_id=current_user.org_id, limit=limit, offset=offset,
        aircraft_model=aircraft_model, system_affected=system_affected,
        recurrence=recurrence, severity=severity,
    )
    return RepairHistoryListResponse(
        repairs=[_repair_to_response(r) for r in repairs],
        total=total, limit=limit, offset=offset,
    )


# ─── Voice Interviews ───

@router.post("/interviews", response_model=VoiceInterviewResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def create_interview(
    request: VoiceInterviewCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    interview = await knowledge_service.create_voice_interview(
        db=db, technician_name=request.technician_name, technician_role=request.technician_role,
        years_experience=request.years_experience, topic=request.topic,
        aircraft_model=request.aircraft_model, system_affected=request.system_affected,
        org_id=current_user.org_id, conducted_by=current_user.user_id,
    )
    return _interview_to_response(interview)


@router.get("/interviews", response_model=VoiceInterviewListResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def list_interviews(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    interviews, total = await knowledge_service.list_voice_interviews(
        db, org_id=current_user.org_id, limit=limit, offset=offset,
    )
    return VoiceInterviewListResponse(
        interviews=[_interview_to_response(i) for i in interviews],
        total=total, limit=limit, offset=offset,
    )


@router.get("/interviews/{interview_id}", response_model=VoiceInterviewResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def get_interview(interview_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from aerumentis.core.database import VoiceInterview
    result = await db.execute(select(VoiceInterview).where(VoiceInterview.id == interview_id))
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return _interview_to_response(interview)


@router.post("/interviews/{interview_id}/transcript", response_model=VoiceInterviewResponse,
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def add_transcript(
    interview_id: str,
    request: TranscriptUpdate,
    db: AsyncSession = Depends(get_db),
):
    interview = await knowledge_service.update_interview_transcript(
        db, interview_id, request.transcript, request.duration_sec, request.language,
    )
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return _interview_to_response(interview)


@router.post("/interviews/{interview_id}/extract", response_model=list[KnowledgeEntryResponse],
             dependencies=[Depends(require_permission(Permission.KNOWLEDGE_WRITE))])
async def extract_knowledge(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Extract structured knowledge entries from an interview transcript using AI."""
    entries = await knowledge_service.extract_knowledge_from_interview(db, interview_id)
    if not entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No knowledge entries could be extracted. Ensure the interview has a transcript.",
        )
    return [_entry_to_response(e) for e in entries]


# ─── Knowledge Graph ───

@router.get("/graph", response_model=KnowledgeGraphResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def get_graph(
    node_types: list[str] | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    graph = await knowledge_service.get_knowledge_graph(
        db, org_id=current_user.org_id, node_types=node_types, limit=limit,
    )
    return KnowledgeGraphResponse(**graph)


# ─── Stats ───

@router.get("/stats", response_model=KnowledgeStatsResponse,
            dependencies=[Depends(require_permission(Permission.KNOWLEDGE_READ))])
async def get_stats(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await knowledge_service.get_knowledge_stats(db, org_id=current_user.org_id)
    return KnowledgeStatsResponse(**stats)
