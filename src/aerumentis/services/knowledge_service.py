"""
Aerumentis — Knowledge Service (Phase 2)
The core intelligence layer for capturing, searching, and connecting institutional knowledge.
"""
from __future__ import annotations

import json
import uuid
from typing import Sequence

from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import (
    KnowledgeEdge, KnowledgeEntry, KnowledgeNode, RepairHistory, VoiceInterview,
)
from aerumentis.core.logging import get_logger
from aerumentis.services.document_processor import chunk_text
from aerumentis.services.embedding_service import get_embedding_service
from aerumentis.services.vector_store import get_vector_store

logger = get_logger("aerumentis.knowledge_service")

KNOWLEDGE_COLLECTION = "knowledge_base"

# Entry types
ENTRY_TYPES = {
    "technician_note", "repair_history", "incident_report",
    "troubleshooting_tip", "best_practice", "safety_advisory",
}


async def ensure_knowledge_collection() -> None:
    """Ensure the knowledge_base collection exists in the vector store."""
    vs = get_vector_store()
    await vs.ensure_collection(KNOWLEDGE_COLLECTION)


# ─── Knowledge Entries ───

async def create_knowledge_entry(
    db: AsyncSession,
    title: str, content: str, entry_type: str = "technician_note",
    aircraft_model: str | None = None, system_affected: str | None = None,
    component_affected: str | None = None, ata_chapter: str | None = None,
    tags: list[str] | None = None,
    author_id: str | None = None, author_name: str | None = None,
    org_id: str | None = None, confidence_score: float = 0.5,
    interview_id: str | None = None,
) -> KnowledgeEntry:
    """Create a knowledge entry and index it in the vector store for semantic search."""
    if entry_type not in ENTRY_TYPES:
        raise ValueError(f"Invalid entry_type. Must be one of: {ENTRY_TYPES}")

    entry = KnowledgeEntry(
        id=str(uuid.uuid4()), title=title, content=content, entry_type=entry_type,
        aircraft_model=aircraft_model, system_affected=system_affected,
        component_affected=component_affected, ata_chapter=ata_chapter,
        tags=",".join(tags) if tags else None,
        author_id=author_id, author_name=author_name, org_id=org_id,
        confidence_score=confidence_score, verified=False,
        interview_id=interview_id,
    )
    db.add(entry)
    await db.flush()

    # Index in vector store
    vector_ids = await _index_entry_in_vector_store(entry)
    if vector_ids:
        entry.vector_ids = json.dumps(vector_ids)
        entry.chunk_count = len(vector_ids)
        await db.flush()

    logger.info("knowledge_entry_created", entry_id=entry.id, title=title[:80], entry_type=entry_type)
    return entry


async def _index_entry_in_vector_store(entry: KnowledgeEntry) -> list[str]:
    """Chunk and embed a knowledge entry, store in Qdrant."""
    try:
        embedding_service = get_embedding_service()
        vector_store = get_vector_store()

        full_text = f"{entry.title}\n\n{entry.content}"
        chunks = chunk_text(full_text)

        points = []
        vector_ids = []
        for idx, chunk_text_content in enumerate(chunks):
            vector = await embedding_service.embed(chunk_text_content)
            point_id = str(uuid.uuid4())
            payload = {
                "text": chunk_text_content, "title": entry.title, "entry_id": entry.id,
                "entry_type": entry.entry_type, "chunk_index": idx,
                "aircraft_model": entry.aircraft_model,
                "system_affected": entry.system_affected,
                "ata_chapter": entry.ata_chapter,
                "tags": entry.tags,
                "author_name": entry.author_name,
                "confidence_score": entry.confidence_score,
                "verified": entry.verified,
                "source": "knowledge_base",
            }
            points.append((point_id, vector, payload))
            vector_ids.append(point_id)

        if points:
            await vector_store.upsert_points(KNOWLEDGE_COLLECTION, points)

        return vector_ids
    except Exception as e:
        logger.warning("vector_index_failed", entry_id=entry.id, error=str(e))
        return []


async def get_knowledge_entry(db: AsyncSession, entry_id: str) -> KnowledgeEntry | None:
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    return result.scalar_one_or_none()


async def list_knowledge_entries(
    db: AsyncSession, org_id: str | None = None, limit: int = 20, offset: int = 0,
    entry_type: str | None = None, aircraft_model: str | None = None,
    system_affected: str | None = None, ata_chapter: str | None = None,
    verified: bool | None = None, status: str = "active",
) -> tuple[Sequence[KnowledgeEntry], int]:
    query = select(KnowledgeEntry).where(KnowledgeEntry.status == status)
    count_q = select(func.count(KnowledgeEntry.id)).where(KnowledgeEntry.status == status)

    if org_id:
        query = query.where(KnowledgeEntry.org_id == org_id)
        count_q = count_q.where(KnowledgeEntry.org_id == org_id)
    if entry_type:
        query = query.where(KnowledgeEntry.entry_type == entry_type)
        count_q = count_q.where(KnowledgeEntry.entry_type == entry_type)
    if aircraft_model:
        query = query.where(KnowledgeEntry.aircraft_model == aircraft_model)
        count_q = count_q.where(KnowledgeEntry.aircraft_model == aircraft_model)
    if system_affected:
        query = query.where(KnowledgeEntry.system_affected == system_affected)
        count_q = count_q.where(KnowledgeEntry.system_affected == system_affected)
    if ata_chapter:
        query = query.where(KnowledgeEntry.ata_chapter == ata_chapter)
        count_q = count_q.where(KnowledgeEntry.ata_chapter == ata_chapter)
    if verified is not None:
        query = query.where(KnowledgeEntry.verified == verified)
        count_q = count_q.where(KnowledgeEntry.verified == verified)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(KnowledgeEntry.created_date.desc()).limit(limit).offset(offset))
    return result.scalars().all(), total


async def update_knowledge_entry(
    db: AsyncSession, entry_id: str, updates: dict,
) -> KnowledgeEntry | None:
    entry = await get_knowledge_entry(db, entry_id)
    if not entry:
        return None
    for key, val in updates.items():
        if hasattr(entry, key) and key != "id":
            if key == "tags" and isinstance(val, list):
                val = ",".join(val)
            setattr(entry, key, val)
    await db.flush()
    logger.info("knowledge_entry_updated", entry_id=entry_id)
    return entry


async def verify_knowledge_entry(
    db: AsyncSession, entry_id: str, verified_by: str,
) -> KnowledgeEntry | None:
    entry = await get_knowledge_entry(db, entry_id)
    if not entry:
        return None
    entry.verified = True
    entry.verified_by = verified_by
    await db.flush()
    await db.refresh(entry)
    logger.info("knowledge_entry_verified", entry_id=entry_id, verified_by=verified_by)
    return entry


async def delete_knowledge_entry(db: AsyncSession, entry_id: str) -> bool:
    entry = await get_knowledge_entry(db, entry_id)
    if not entry:
        return False
    # Remove from vector store
    if entry.vector_ids:
        try:
            vector_ids = json.loads(entry.vector_ids)
            vs = get_vector_store()
            await vs.delete_points(KNOWLEDGE_COLLECTION, vector_ids)
        except Exception as e:
            logger.warning("vector_delete_failed", entry_id=entry_id, error=str(e))
    entry.status = "archived"
    await db.flush()
    logger.info("knowledge_entry_archived", entry_id=entry_id)
    return True


# ─── Semantic Search ───

async def search_knowledge(
    db: AsyncSession, query: str, org_id: str | None = None,
    top_k: int = 10, score_threshold: float = 0.55,
    aircraft_model: str | None = None, entry_type: str | None = None,
    verified_only: bool = False,
) -> list[dict]:
    """Semantic search across the knowledge base."""
    try:
        embedding_service = get_embedding_service()
        vector_store = get_vector_store()

        query_vector = await embedding_service.embed(query)
        filters: dict = {"source": "knowledge_base"}
        if aircraft_model:
            filters["aircraft_model"] = aircraft_model
        if entry_type:
            filters["entry_type"] = entry_type
        if verified_only:
            filters["verified"] = True

        results = await vector_store.search(
            collection_name=KNOWLEDGE_COLLECTION, query_vector=query_vector,
            top_k=top_k, score_threshold=score_threshold, filters=filters if filters else None,
        )

        search_results = []
        for r in results:
            search_results.append({
                "chunk_id": r.id, "score": r.score,
                "entry_id": r.payload.get("entry_id", ""),
                "title": r.payload.get("title", ""),
                "text": r.payload.get("text", "")[:2000],
                "entry_type": r.payload.get("entry_type", ""),
                "aircraft_model": r.payload.get("aircraft_model"),
                "system_affected": r.payload.get("system_affected"),
                "ata_chapter": r.payload.get("ata_chapter"),
                "author_name": r.payload.get("author_name"),
                "confidence_score": r.payload.get("confidence_score", 0.5),
                "verified": r.payload.get("verified", False),
            })
        return search_results
    except Exception as e:
        logger.warning("knowledge_search_failed", error=str(e))
        return []


# ─── Pattern Matching ("Have we seen this before?") ───

async def find_similar_issues(
    db: AsyncSession, symptom: str, org_id: str | None = None,
    aircraft_model: str | None = None, system_affected: str | None = None,
    top_k: int = 15,
) -> dict:
    """
    The killer feature: "Have we seen this fuel pressure issue before?"
    Searches knowledge base + repair history, aggregates patterns, and returns
    a summary with occurrence counts and most common causes.
    """
    # Semantic search across knowledge base
    search_query = symptom
    if aircraft_model:
        search_query += f" aircraft {aircraft_model}"
    if system_affected:
        search_query += f" system {system_affected}"

    kb_results = await search_knowledge(
        db, search_query, org_id=org_id, top_k=top_k, score_threshold=0.50,
        aircraft_model=aircraft_model,
    )

    # Also search repair history in DB
    repair_query = select(RepairHistory).where(RepairHistory.symptom.ilike(f"%{symptom}%"))
    if org_id:
        repair_query = repair_query.where(RepairHistory.org_id == org_id)
    if aircraft_model:
        repair_query = repair_query.where(RepairHistory.aircraft_model == aircraft_model)
    if system_affected:
        repair_query = repair_query.where(RepairHistory.system_affected == system_affected)
    repair_result = await db.execute(repair_query.limit(top_k))
    repairs = repair_result.scalars().all()

    # Aggregate patterns from knowledge entries
    causes: dict[str, int] = {}
    resolutions: dict[str, int] = {}
    related_entries = []

    for r in kb_results:
        related_entries.append({
            "entry_id": r["entry_id"], "title": r["title"], "score": r["score"],
            "entry_type": r["entry_type"], "text": r["text"][:500],
            "aircraft_model": r["aircraft_model"], "verified": r["verified"],
        })

    for repair in repairs:
        cause_key = repair.diagnosis[:100]
        causes[cause_key] = causes.get(cause_key, 0) + 1
        res_key = repair.resolution[:100]
        resolutions[res_key] = resolutions.get(res_key, 0) + 1

    # Sort by frequency
    top_causes = sorted(causes.items(), key=lambda x: x[1], reverse=True)[:5]
    top_resolutions = sorted(resolutions.items(), key=lambda x: x[1], reverse=True)[:5]

    total_occurrences = len(kb_results) + len(repairs)

    result = {
        "query": symptom,
        "total_occurrences": total_occurrences,
        "knowledge_base_matches": len(kb_results),
        "repair_history_matches": len(repairs),
        "most_common_causes": [{"cause": c, "occurrences": n} for c, n in top_causes],
        "most_common_resolutions": [{"resolution": r, "occurrences": n} for r, n in top_resolutions],
        "related_entries": related_entries[:10],
        "related_repairs": [
            {
                "id": r.id, "aircraft_tail": r.aircraft_tail_number, "symptom": r.symptom[:200],
                "diagnosis": r.diagnosis[:200], "resolution": r.resolution[:200],
                "recurrence": r.recurrence, "severity": r.severity,
                "technician_name": r.technician_name, "created_date": r.created_date.isoformat(),
            }
            for r in repairs[:10]
        ],
        "summary": _generate_pattern_summary(total_occurrences, top_causes, top_resolutions),
    }
    logger.info("pattern_match", symptom=symptom[:80], occurrences=total_occurrences,
                kb_matches=len(kb_results), repair_matches=len(repairs))
    return result


def _generate_pattern_summary(total: int, causes: list, resolutions: list) -> str:
    if total == 0:
        return "No similar occurrences found in the knowledge base. This appears to be a new issue."
    parts = [f"{total} similar occurrence{'s' if total != 1 else ''} found."]
    if causes:
        top_cause = causes[0]
        parts.append(f"Most commonly caused by: {top_cause[0]} ({top_cause[1]} occurrences).")
    if resolutions:
        top_res = resolutions[0]
        parts.append(f"Most common resolution: {top_res[0]} ({top_res[1]} occurrences).")
    return " ".join(parts)


# ─── Repair History ───

async def create_repair_history(
    db: AsyncSession,
    aircraft_tail_number: str | None = None, aircraft_model: str | None = None,
    system_affected: str | None = None, component_affected: str | None = None,
    ata_chapter: str | None = None, symptom: str = "", diagnosis: str = "",
    resolution: str = "", parts_replaced: str | None = None,
    labor_hours: float | None = None, downtime_hours: float | None = None,
    recurrence: str = "first_occurrence", severity: str = "minor",
    technician_id: str | None = None, technician_name: str | None = None,
    org_id: str | None = None,
) -> RepairHistory:
    """Create a repair history record and auto-check for pattern matches."""
    # Check for similar past repairs
    pattern_count = 0
    if symptom:
        existing = await db.execute(
            select(func.count(RepairHistory.id)).where(
                RepairHistory.symptom.ilike(f"%{symptom[:50]}%"),
                RepairHistory.org_id == org_id if org_id else RepairHistory.org_id.is_(None),
            )
        )
        pattern_count = (existing.scalar() or 0)
        if pattern_count > 0:
            recurrence = "recurring" if pattern_count < 5 else "chronic"

    repair = RepairHistory(
        id=str(uuid.uuid4()),
        aircraft_tail_number=aircraft_tail_number, aircraft_model=aircraft_model,
        system_affected=system_affected, component_affected=component_affected,
        ata_chapter=ata_chapter, symptom=symptom, diagnosis=diagnosis,
        resolution=resolution, parts_replaced=parts_replaced,
        labor_hours=labor_hours, downtime_hours=downtime_hours,
        recurrence=recurrence, severity=severity,
        technician_id=technician_id, technician_name=technician_name,
        org_id=org_id, pattern_match_count=pattern_count,
    )
    db.add(repair)
    await db.flush()

    # Also create a knowledge entry from this repair
    title = f"Repair: {symptom[:60]} — {aircraft_model or 'Unknown aircraft'}"
    content = f"Symptom: {symptom}\nDiagnosis: {diagnosis}\nResolution: {resolution}"
    if parts_replaced:
        content += f"\nParts Replaced: {parts_replaced}"
    if aircraft_tail_number:
        content += f"\nAircraft: {aircraft_tail_number}"

    entry = await create_knowledge_entry(
        db, title=title, content=content, entry_type="repair_history",
        aircraft_model=aircraft_model, system_affected=system_affected,
        component_affected=component_affected, ata_chapter=ata_chapter,
        tags=[recurrence, severity] if recurrence != "first_occurrence" else [severity],
        author_id=technician_id, author_name=technician_name, org_id=org_id,
        confidence_score=0.8 if recurrence == "first_occurrence" else 0.9,
    )
    repair.knowledge_entry_id = entry.id
    await db.flush()

    logger.info("repair_history_created", repair_id=repair.id, pattern_count=pattern_count,
                recurrence=recurrence)
    return repair


async def list_repair_history(
    db: AsyncSession, org_id: str | None = None, limit: int = 20, offset: int = 0,
    aircraft_model: str | None = None, system_affected: str | None = None,
    recurrence: str | None = None, severity: str | None = None,
) -> tuple[Sequence[RepairHistory], int]:
    query = select(RepairHistory)
    count_q = select(func.count(RepairHistory.id))

    if org_id:
        query = query.where(RepairHistory.org_id == org_id)
        count_q = count_q.where(RepairHistory.org_id == org_id)
    if aircraft_model:
        query = query.where(RepairHistory.aircraft_model == aircraft_model)
        count_q = count_q.where(RepairHistory.aircraft_model == aircraft_model)
    if system_affected:
        query = query.where(RepairHistory.system_affected == system_affected)
        count_q = count_q.where(RepairHistory.system_affected == system_affected)
    if recurrence:
        query = query.where(RepairHistory.recurrence == recurrence)
        count_q = count_q.where(RepairHistory.recurrence == recurrence)
    if severity:
        query = query.where(RepairHistory.severity == severity)
        count_q = count_q.where(RepairHistory.severity == severity)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(RepairHistory.created_date.desc()).limit(limit).offset(offset))
    return result.scalars().all(), total


# ─── Voice Interviews ───

async def create_voice_interview(
    db: AsyncSession,
    technician_name: str, topic: str,
    technician_role: str | None = None, years_experience: int | None = None,
    aircraft_model: str | None = None, system_affected: str | None = None,
    org_id: str | None = None, conducted_by: str | None = None,
) -> VoiceInterview:
    interview = VoiceInterview(
        id=str(uuid.uuid4()),
        technician_name=technician_name, technician_role=technician_role,
        years_experience=years_experience, topic=topic,
        aircraft_model=aircraft_model, system_affected=system_affected,
        org_id=org_id, conducted_by=conducted_by,
        status="pending_upload",
    )
    db.add(interview)
    await db.flush()
    logger.info("voice_interview_created", interview_id=interview.id, technician=technician_name)
    return interview


async def update_interview_transcript(
    db: AsyncSession, interview_id: str, transcript: str,
    duration_sec: float = 0.0, language: str = "en",
) -> VoiceInterview | None:
    result = await db.execute(select(VoiceInterview).where(VoiceInterview.id == interview_id))
    interview = result.scalar_one_or_none()
    if not interview:
        return None
    interview.transcript = transcript
    interview.transcript_language = language
    interview.transcript_word_count = len(transcript.split())
    interview.audio_duration_sec = duration_sec
    interview.status = "transcribed"
    await db.flush()
    await db.refresh(interview)
    logger.info("interview_transcribed", interview_id=interview_id,
                word_count=interview.transcript_word_count)
    return interview


async def extract_knowledge_from_interview(
    db: AsyncSession, interview_id: str,
) -> list[KnowledgeEntry]:
    """
    Use LLM to extract structured knowledge entries from an interview transcript.
    The LLM identifies key insights, procedures, tips, and warnings.
    """
    result = await db.execute(select(VoiceInterview).where(VoiceInterview.id == interview_id))
    interview = result.scalar_one_or_none()
    if not interview or not interview.transcript:
        return []

    interview.status = "extracting"
    await db.flush()

    try:
        from aerumentis.services.llm_service import get_llm_service
        llm = get_llm_service()

        extraction_prompt = f"""You are an aerospace maintenance knowledge extraction system.
Analyze this interview transcript with a {interview.technician_role or "technician"} about "{interview.topic}".
Extract distinct, actionable knowledge entries. For each entry, provide:
1. A concise title (max 100 chars)
2. The content (the actual knowledge — procedure, tip, warning, or insight)
3. The entry type (one of: technician_note, troubleshooting_tip, best_practice, safety_advisory)
4. The system affected (if identifiable)
5. Tags (comma-separated keywords)

Format each entry as JSON on its own line:
{{"title": "...", "content": "...", "entry_type": "...", "system_affected": "...", "tags": ["...", "..."]}}

Transcript:
{interview.transcript[:8000]}

Extract as many distinct knowledge entries as you can find. Output one JSON object per line."""

        response = await llm.generate(extraction_prompt, temperature=0.3)

        entries_created = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                entry = await create_knowledge_entry(
                    db=db,
                    title=data.get("title", "Extracted Knowledge")[:500],
                    content=data.get("content", ""),
                    entry_type=data.get("entry_type", "technician_note"),
                    aircraft_model=interview.aircraft_model,
                    system_affected=data.get("system_affected") or interview.system_affected,
                    tags=data.get("tags", []),
                    author_name=interview.technician_name,
                    org_id=interview.org_id,
                    interview_id=interview_id,
                    confidence_score=0.7,  # AI-extracted, slightly lower confidence
                )
                entries_created.append(entry)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("interview_extraction_parse_error", line=line[:50], error=str(e))
                continue

        interview.status = "completed"
        interview.entries_created = len(entries_created)
        await db.flush()
        logger.info("interview_knowledge_extracted", interview_id=interview_id,
                    entries_created=len(entries_created))
        return entries_created

    except Exception as e:
        interview.status = "failed"
        interview.processing_error = str(e)
        await db.flush()
        logger.error("interview_extraction_failed", interview_id=interview_id, error=str(e))
        return []


async def list_voice_interviews(
    db: AsyncSession, org_id: str | None = None, limit: int = 20, offset: int = 0,
) -> tuple[Sequence[VoiceInterview], int]:
    query = select(VoiceInterview)
    count_q = select(func.count(VoiceInterview.id))
    if org_id:
        query = query.where(VoiceInterview.org_id == org_id)
        count_q = count_q.where(VoiceInterview.org_id == org_id)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(VoiceInterview.created_date.desc()).limit(limit).offset(offset))
    return result.scalars().all(), total


# ─── Knowledge Graph ───

async def get_or_create_node(
    db: AsyncSession, node_type: str, label: str, org_id: str | None = None,
    description: str | None = None,
) -> KnowledgeNode:
    result = await db.execute(
        select(KnowledgeNode).where(
            KnowledgeNode.node_type == node_type,
            KnowledgeNode.label == label,
            KnowledgeNode.org_id == org_id if org_id else KnowledgeNode.org_id.is_(None),
        )
    )
    node = result.scalar_one_or_none()
    if node:
        return node
    node = KnowledgeNode(
        id=str(uuid.uuid4()), node_type=node_type, label=label,
        description=description, org_id=org_id,
    )
    db.add(node)
    await db.flush()
    return node


async def create_edge(
    db: AsyncSession, source_node_id: str, target_node_id: str,
    edge_type: str, weight: float = 1.0, source_entry_id: str | None = None,
) -> KnowledgeEdge:
    # Check if edge already exists — if so, increment evidence count
    result = await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.source_node_id == source_node_id,
            KnowledgeEdge.target_node_id == target_node_id,
            KnowledgeEdge.edge_type == edge_type,
        )
    )
    edge = result.scalar_one_or_none()
    if edge:
        edge.evidence_count += 1
        edge.weight = min(edge.weight + 0.1, 1.0)
        if source_entry_id:
            existing_ids = json.loads(edge.source_entry_ids) if edge.source_entry_ids else []
            if source_entry_id not in existing_ids:
                existing_ids.append(source_entry_id)
                edge.source_entry_ids = json.dumps(existing_ids)
        await db.flush()
        return edge

    edge = KnowledgeEdge(
        id=str(uuid.uuid4()),
        source_node_id=source_node_id, target_node_id=target_node_id,
        edge_type=edge_type, weight=weight,
        source_entry_ids=json.dumps([source_entry_id]) if source_entry_id else None,
    )
    db.add(edge)
    await db.flush()
    return edge


async def get_knowledge_graph(
    db: AsyncSession, org_id: str | None = None, node_types: list[str] | None = None,
    limit: int = 100,
) -> dict:
    """Return the knowledge graph as nodes + edges for visualization."""
    node_query = select(KnowledgeNode)
    if org_id:
        node_query = node_query.where(KnowledgeNode.org_id == org_id)
    if node_types:
        node_query = node_query.where(KnowledgeNode.node_type.in_(node_types))
    node_query = node_query.limit(limit)

    nodes_result = await db.execute(node_query)
    nodes = nodes_result.scalars().all()
    node_ids = [n.id for n in nodes]

    if not node_ids:
        return {"nodes": [], "edges": []}

    edges_result = await db.execute(
        select(KnowledgeEdge).where(
            or_(
                KnowledgeEdge.source_node_id.in_(node_ids),
                KnowledgeEdge.target_node_id.in_(node_ids),
            )
        ).limit(limit * 5)
    )
    edges = edges_result.scalars().all()

    return {
        "nodes": [
            {
                "id": n.id, "type": n.node_type, "label": n.label,
                "description": n.description, "occurrence_count": n.occurrence_count,
                "last_seen": n.last_seen,
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id, "source": e.source_node_id, "target": e.target_node_id,
                "type": e.edge_type, "weight": e.weight, "evidence_count": e.evidence_count,
            }
            for e in edges
        ],
    }


# ─── Statistics ───

async def get_knowledge_stats(db: AsyncSession, org_id: str | None = None) -> dict:
    base_q = select(KnowledgeEntry).where(KnowledgeEntry.status == "active")
    if org_id:
        base_q = base_q.where(KnowledgeEntry.org_id == org_id)
    result = await db.execute(base_q)
    entries = result.scalars().all()

    by_type: dict[str, int] = {}
    by_aircraft: dict[str, int] = {}
    by_system: dict[str, int] = {}
    verified_count = 0
    from_interviews = 0

    for e in entries:
        by_type[e.entry_type] = by_type.get(e.entry_type, 0) + 1
        if e.aircraft_model:
            by_aircraft[e.aircraft_model] = by_aircraft.get(e.aircraft_model, 0) + 1
        if e.system_affected:
            by_system[e.system_affected] = by_system.get(e.system_affected, 0) + 1
        if e.verified:
            verified_count += 1
        if e.interview_id:
            from_interviews += 1

    # Repair stats
    repair_q = select(RepairHistory)
    if org_id:
        repair_q = repair_q.where(RepairHistory.org_id == org_id)
    repair_result = await db.execute(repair_q)
    repairs = repair_result.scalars().all()

    recurring = sum(1 for r in repairs if r.recurrence == "recurring")
    chronic = sum(1 for r in repairs if r.recurrence == "chronic")

    # Interview stats
    interview_q = select(VoiceInterview)
    if org_id:
        interview_q = interview_q.where(VoiceInterview.org_id == org_id)
    interview_result = await db.execute(interview_q)
    interviews = interview_result.scalars().all()

    return {
        "total_entries": len(entries),
        "by_type": by_type,
        "by_aircraft_model": by_aircraft,
        "by_system": by_system,
        "verified_entries": verified_count,
        "from_interviews": from_interviews,
        "total_repairs": len(repairs),
        "recurring_issues": recurring,
        "chronic_issues": chronic,
        "total_interviews": len(interviews),
        "completed_interviews": sum(1 for i in interviews if i.status == "completed"),
        "total_interview_word_count": sum(i.transcript_word_count for i in interviews),
    }
