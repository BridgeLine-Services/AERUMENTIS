"""Aerumentis — Document Router (upload and manage maintenance docs)."""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from aerumentis.core.database import get_db
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.logging import get_logger
from aerumentis.core.security import AuthenticatedUser, Permission, get_current_user, require_permission
from aerumentis.models.schemas import (
    DocumentListResponse, DocumentMetadataResponse, DocumentStatsResponse,
    IngestionResponse, MessageResponse,
)
from aerumentis.services.document_metadata_service import (
    create_document, get_document, get_document_stats, list_documents, mark_document_deleted,
)
from aerumentis.services.document_processor import SUPPORTED_EXTENSIONS
from aerumentis.services.ingestion_service import get_ingestion_service

router = APIRouter(prefix="/documents", tags=["documents"])
logger = get_logger("aerumentis.api.documents")
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


@router.post("/upload", response_model=IngestionResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.DOCUMENT_UPLOAD))])
async def upload_document(
    file: UploadFile = File(...),
    aircraft_model: str | None = Form(None),
    manual_type: str | None = Form(None),
    manual_number: str | None = Form(None),
    revision: str | None = Form(None),
    effective_date: str | None = Form(None),
    tags: str | None = Form(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "unknown"
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    content = await file.read()
    file_size = len(content)
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    extra_metadata: dict = {}
    if aircraft_model: extra_metadata["aircraft_model"] = aircraft_model
    if manual_type: extra_metadata["manual_type"] = manual_type
    if manual_number: extra_metadata["manual_number"] = manual_number
    if revision: extra_metadata["revision"] = revision
    if effective_date: extra_metadata["effective_date"] = effective_date
    if tag_list: extra_metadata["tags"] = tag_list

    ingestion_service = get_ingestion_service()
    result = await ingestion_service.ingest_bytes(content=content, filename=filename, extra_metadata=extra_metadata)

    # Persist document metadata to database
    if result.status == "success":
        await create_document(
            db=db, document_id=result.document_id, filename=filename, file_type=ext,
            file_size=file_size, checksum=result.checksum, chunk_count=result.chunk_count,
            total_tokens=result.total_tokens, status="active",
            aircraft_model=aircraft_model, manual_type=manual_type, manual_number=manual_number,
            revision=revision, effective_date=effective_date, tags=tag_list,
            org_id=current_user.org_id, uploaded_by=current_user.user_id,
        )
        return IngestionResponse(
            document_id=result.document_id, filename=result.filename, chunk_count=result.chunk_count,
            total_tokens=result.total_tokens, checksum=result.checksum, status="success",
            message=f"Successfully ingested {result.chunk_count} chunks from {filename}",
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"document_id": "", "filename": filename, "chunk_count": 0, "total_tokens": 0,
                 "checksum": "", "status": "failed", "error": result.error, "message": "Document processing failed"},
    )


@router.post("/upload-batch", response_model=list[IngestionResponse], status_code=201,
             dependencies=[Depends(require_permission(Permission.DOCUMENT_UPLOAD))])
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    aircraft_model: str | None = Form(None),
    manual_type: str | None = Form(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if len(files) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 20 files per batch upload")
    results: list[IngestionResponse] = []
    ingestion_service = get_ingestion_service()
    for file in files:
        filename = file.filename or "unknown"
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in SUPPORTED_EXTENSIONS:
            results.append(IngestionResponse(document_id="", filename=filename, chunk_count=0,
                         total_tokens=0, checksum="", status="failed", error=f"Unsupported type: {ext}"))
            continue
        content = await file.read()
        file_size = len(content)
        extra_metadata = {}
        if aircraft_model: extra_metadata["aircraft_model"] = aircraft_model
        if manual_type: extra_metadata["manual_type"] = manual_type
        result = await ingestion_service.ingest_bytes(content=content, filename=filename, extra_metadata=extra_metadata)
        if result.status == "success":
            await create_document(
                db=db, document_id=result.document_id, filename=filename, file_type=ext,
                file_size=file_size, checksum=result.checksum, chunk_count=result.chunk_count,
                total_tokens=result.total_tokens, status="active",
                aircraft_model=aircraft_model, manual_type=manual_type,
                org_id=current_user.org_id, uploaded_by=current_user.user_id,
            )
        results.append(IngestionResponse(
            document_id=result.document_id, filename=result.filename, chunk_count=result.chunk_count,
            total_tokens=result.total_tokens, checksum=result.checksum, status=result.status,
            error=result.error, message="Success" if result.status == "success" else "Failed",
        ))
    return results


@router.get("/", response_model=DocumentListResponse,
            dependencies=[Depends(require_permission(Permission.DOCUMENT_READ))])
async def list_all_documents(
    aircraft_model: str | None = Query(None),
    manual_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    docs, total = await list_documents(
        db, org_id=current_user.org_id, limit=limit, offset=offset,
        aircraft_model=aircraft_model, manual_type=manual_type,
    )
    return DocumentListResponse(
        documents=[DocumentMetadataResponse(
            id=d.id, filename=d.filename, file_type=d.file_type, chunk_count=d.chunk_count,
            total_tokens=d.total_tokens, status=d.status, aircraft_model=d.aircraft_model,
            manual_type=d.manual_type, manual_number=d.manual_number, revision=d.revision,
            effective_date=d.effective_date,
            tags=d.tags.split(",") if d.tags else [],
            created_date=d.created_date, updated_date=d.updated_date,
        ) for d in docs],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentMetadataResponse,
            dependencies=[Depends(require_permission(Permission.DOCUMENT_READ))])
async def get_document_metadata(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")
    return DocumentMetadataResponse(
        id=doc.id, filename=doc.filename, file_type=doc.file_type, chunk_count=doc.chunk_count,
        total_tokens=doc.total_tokens, status=doc.status, aircraft_model=doc.aircraft_model,
        manual_type=doc.manual_type, manual_number=doc.manual_number, revision=doc.revision,
        effective_date=doc.effective_date, tags=doc.tags.split(",") if doc.tags else [],
        created_date=doc.created_date, updated_date=doc.updated_date,
    )


@router.delete("/{document_id}", response_model=MessageResponse,
               dependencies=[Depends(require_permission(Permission.DOCUMENT_DELETE))])
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    ingestion_service = get_ingestion_service()
    await ingestion_service.delete_document(document_id)
    success = await mark_document_deleted(db, document_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")
    return MessageResponse(message=f"Document {document_id} deleted successfully")


@router.get("/stats/summary", response_model=DocumentStatsResponse,
            dependencies=[Depends(require_permission(Permission.DOCUMENT_READ))])
async def document_stats_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_document_stats(db, org_id=current_user.org_id)
    return DocumentStatsResponse(**stats)
