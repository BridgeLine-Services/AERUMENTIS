"""Aerumentis — Document Router (upload and manage maintenance docs)."""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from aerumentis.core.logging import get_logger
from aerumentis.core.security import Permission, get_current_user, require_permission
from aerumentis.models.schemas import IngestionResponse, MessageResponse
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
):
    filename = file.filename or "unknown"
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)} MB")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    extra_metadata: dict = {}
    if aircraft_model: extra_metadata["aircraft_model"] = aircraft_model
    if manual_type: extra_metadata["manual_type"] = manual_type
    if manual_number: extra_metadata["manual_number"] = manual_number
    if revision: extra_metadata["revision"] = revision
    if effective_date: extra_metadata["effective_date"] = effective_date
    if tags: extra_metadata["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    ingestion_service = get_ingestion_service()
    result = await ingestion_service.ingest_bytes(content=content, filename=filename, extra_metadata=extra_metadata)
    if result.status == "failed":
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            content=IngestionResult_model(result, filename))
    return IngestionResponse(document_id=result.document_id, filename=result.filename,
                             chunk_count=result.chunk_count, total_tokens=result.total_tokens,
                             checksum=result.checksum, status="success",
                             message=f"Successfully ingested {result.chunk_count} chunks from {filename}")


def IngestionResult_model(result, filename):
    return {"document_id": "", "filename": filename, "chunk_count": 0, "total_tokens": 0,
            "checksum": "", "status": "failed", "error": result.error, "message": "Document processing failed"}


@router.post("/upload-batch", response_model=list[IngestionResponse], status_code=201,
             dependencies=[Depends(require_permission(Permission.DOCUMENT_UPLOAD))])
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    aircraft_model: str | None = Form(None), manual_type: str | None = Form(None),
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
        extra_metadata = {}
        if aircraft_model: extra_metadata["aircraft_model"] = aircraft_model
        if manual_type: extra_metadata["manual_type"] = manual_type
        result = await ingestion_service.ingest_bytes(content=content, filename=filename, extra_metadata=extra_metadata)
        results.append(IngestionResponse(document_id=result.document_id, filename=result.filename,
                     chunk_count=result.chunk_count, total_tokens=result.total_tokens, checksum=result.checksum,
                     status=result.status, error=result.error,
                     message="Success" if result.status == "success" else "Failed"))
    return results


@router.delete("/{document_id}", response_model=MessageResponse,
               dependencies=[Depends(require_permission(Permission.DOCUMENT_DELETE))])
async def delete_document(document_id: str):
    ingestion_service = get_ingestion_service()
    success = await ingestion_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")
    return MessageResponse(message=f"Document {document_id} deleted successfully")


@router.get("/stats", dependencies=[Depends(require_permission(Permission.DOCUMENT_READ))])
async def document_stats():
    from aerumentis.services.vector_store import get_vector_store
    vs = get_vector_store()
    count = await vs.count("maintenance_docs")
    return {"total_documents": count, "collection": "maintenance_docs", "vector_store": "qdrant"}
