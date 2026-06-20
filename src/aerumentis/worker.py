"""Aerumentis — Celery Worker for async task processing."""
from __future__ import annotations

import asyncio
from typing import Any

from celery import Celery

from aerumentis.core.config import get_settings

settings = get_settings()

celery_app = Celery("aerumentis", broker=settings.celery_broker_url, backend=settings.celery_result_backend)

celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    timezone="UTC", enable_utc=True, task_track_started=True,
    task_time_limit=600, task_soft_time_limit=480,
    worker_prefetch_multiplier=1, worker_max_tasks_per_child=100,
    task_routes={
        "aerumentis.tasks.ingest_document": {"queue": "ingestion"},
        "aerumentis.tasks.ingest_document_batch": {"queue": "ingestion"},
    },
)


@celery_app.task(name="aerumentis.tasks.ingest_document", bind=True)
def ingest_document_task(self, file_path: str, filename: str, extra_metadata: dict[str, Any] | None = None) -> dict:
    from aerumentis.services.ingestion_service import get_ingestion_service

    async def _run():
        service = get_ingestion_service()
        result = await service.ingest_file(file_path=file_path, filename=filename, extra_metadata=extra_metadata)
        return {"document_id": result.document_id, "filename": result.filename,
                "chunk_count": result.chunk_count, "total_tokens": result.total_tokens,
                "checksum": result.checksum, "status": result.status, "error": result.error}
    return asyncio.run(_run())


@celery_app.task(name="aerumentis.tasks.ingest_document_batch", bind=True)
def ingest_document_batch_task(self, files: list[dict[str, Any]]) -> list[dict]:
    from aerumentis.services.ingestion_service import get_ingestion_service

    async def _run():
        service = get_ingestion_service()
        results = []
        for f in files:
            result = await service.ingest_file(file_path=f["file_path"], filename=f["filename"],
                                                extra_metadata=f.get("extra_metadata"))
            results.append({"document_id": result.document_id, "filename": result.filename,
                           "chunk_count": result.chunk_count, "total_tokens": result.total_tokens,
                           "status": result.status, "error": result.error})
        return results
    return asyncio.run(_run())


@celery_app.task(name="aerumentis.tasks.health_check")
def health_check_task() -> dict:
    return {"status": "healthy", "worker": "aerumentis-celery"}
