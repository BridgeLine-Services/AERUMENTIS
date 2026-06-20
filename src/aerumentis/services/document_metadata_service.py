"""
Aerumentis — Document Metadata Service
Persist and query document metadata from the database.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import Document
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.document_metadata")


async def create_document(
    db: AsyncSession,
    document_id: str, filename: str, file_type: str, file_size: int,
    checksum: str, chunk_count: int, total_tokens: int,
    status: str = "active", error: str | None = None,
    aircraft_model: str | None = None, manual_type: str | None = None,
    manual_number: str | None = None, revision: str | None = None,
    effective_date: str | None = None, tags: list[str] | None = None,
    org_id: str | None = None, uploaded_by: str | None = None,
) -> Document:
    doc = Document(
        id=document_id, filename=filename, file_type=file_type, file_size=file_size,
        checksum=checksum, chunk_count=chunk_count, total_tokens=total_tokens,
        status=status, error=error, aircraft_model=aircraft_model,
        manual_type=manual_type, manual_number=manual_number, revision=revision,
        effective_date=effective_date, tags=",".join(tags) if tags else None,
        org_id=org_id, uploaded_by=uploaded_by,
    )
    db.add(doc)
    await db.flush()
    logger.info("document_metadata_saved", document_id=document_id, filename=filename)
    return doc


async def get_document(db: AsyncSession, document_id: str) -> Document | None:
    result = await db.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()


async def list_documents(
    db: AsyncSession, org_id: str | None = None, limit: int = 50, offset: int = 0,
    aircraft_model: str | None = None, manual_type: str | None = None,
    status: str = "active",
) -> tuple[Sequence[Document], int]:
    query = select(Document).where(Document.status == status)
    count_query = select(func.count(Document.id)).where(Document.status == status)

    if org_id:
        query = query.where(Document.org_id == org_id)
        count_query = count_query.where(Document.org_id == org_id)
    if aircraft_model:
        query = query.where(Document.aircraft_model == aircraft_model)
        count_query = count_query.where(Document.aircraft_model == aircraft_model)
    if manual_type:
        query = query.where(Document.manual_type == manual_type)
        count_query = count_query.where(Document.manual_type == manual_type)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Document.created_date.desc()).limit(limit).offset(offset))
    return result.scalars().all(), total


async def mark_document_deleted(db: AsyncSession, document_id: str) -> bool:
    result = await db.execute(
        update(Document).where(Document.id == document_id).values(status="deleted").returning(Document.id)
    )
    row = result.scalar_one_or_none()
    if row:
        logger.info("document_marked_deleted", document_id=document_id)
        return True
    return False


async def get_document_stats(db: AsyncSession, org_id: str | None = None) -> dict:
    query = select(Document).where(Document.status == "active")
    if org_id:
        query = query.where(Document.org_id == org_id)

    result = await db.execute(query)
    docs = result.scalars().all()

    aircraft_models: dict[str, int] = {}
    manual_types: dict[str, int] = {}
    total_chunks = 0
    total_tokens = 0

    for doc in docs:
        if doc.aircraft_model:
            aircraft_models[doc.aircraft_model] = aircraft_models.get(doc.aircraft_model, 0) + 1
        if doc.manual_type:
            manual_types[doc.manual_type] = manual_types.get(doc.manual_type, 0) + 1
        total_chunks += doc.chunk_count
        total_tokens += doc.total_tokens

    return {
        "total_documents": len(docs),
        "total_chunks": total_chunks,
        "total_tokens": total_tokens,
        "by_aircraft_model": aircraft_models,
        "by_manual_type": manual_types,
    }
