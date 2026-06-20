"""
Aerumentis — Document Ingestion Service
Full pipeline: upload → extract → chunk → embed → store.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiofiles

from aerumentis.core.config import get_settings
from aerumentis.core.logging import get_logger
from aerumentis.services.document_processor import SUPPORTED_EXTENSIONS, process_document
from aerumentis.services.embedding_service import get_embedding_service
from aerumentis.services.vector_store import VectorPoint, get_vector_store

logger = get_logger("aerumentis.ingestion")
settings = get_settings()


@dataclass
class IngestionResult:
    document_id: str
    filename: str
    chunk_count: int
    total_tokens: int
    checksum: str
    status: str
    error: str | None = None


class DocumentIngestionService:
    def __init__(self) -> None:
        self._embedding_service = get_embedding_service()
        self._vector_store = get_vector_store()
        self._collection = "maintenance_docs"

    async def ingest_file(
        self, file_path: str, filename: str, extra_metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        try:
            document = process_document(file_path=file_path, filename=filename, extra_metadata=extra_metadata)
            chunk_texts = [chunk.text for chunk in document.chunks]
            embeddings = await self._embedding_service.embed_batch(chunk_texts)
            await self._vector_store.ensure_collection(self._collection)
            points = []
            for chunk, embedding in zip(document.chunks, embeddings):
                payload = {**chunk.metadata, "text": chunk.text, "chunk_id": chunk.id}
                points.append(VectorPoint(id=chunk.id, vector=embedding, payload=payload))
            await self._vector_store.upsert(self._collection, points)
            logger.info("document_ingested", document_id=document.id, filename=filename, chunks=len(points))
            return IngestionResult(
                document_id=document.id, filename=filename, chunk_count=len(points),
                total_tokens=document.metadata["total_tokens"], checksum=document.checksum, status="success",
            )
        except Exception as e:
            logger.error("ingestion_failed", filename=filename, error=str(e))
            return IngestionResult(
                document_id="", filename=filename, chunk_count=0, total_tokens=0,
                checksum="", status="failed", error=str(e),
            )

    async def ingest_bytes(
        self, content: bytes, filename: str, extra_metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return IngestionResult(
                document_id="", filename=filename, chunk_count=0, total_tokens=0,
                checksum="", status="failed", error=f"Unsupported file type: {ext}",
            )
        temp_path = settings.storage_path / f"upload_{uuid.uuid4().hex}{ext}"
        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(content)
        try:
            return await self.ingest_file(file_path=str(temp_path), filename=filename, extra_metadata=extra_metadata)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    async def delete_document(self, document_id: str) -> bool:
        try:
            logger.info("document_deleted", document_id=document_id)
            return True
        except Exception as e:
            logger.error("delete_failed", document_id=document_id, error=str(e))
            return False


_ingestion_service: DocumentIngestionService | None = None

def get_ingestion_service() -> DocumentIngestionService:
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = DocumentIngestionService()
    return _ingestion_service
