"""Aerumentis — Health Check Router."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from aerumentis.core.config import get_settings
from aerumentis.models.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])
settings = get_settings()


@router.get("/", response_model=HealthResponse)
@router.get("", response_model=HealthResponse)
async def health_check():
    services: dict[str, str] = {}
    try:
        from aerumentis.services.vector_store import get_vector_store
        vs = get_vector_store()
        services["vector_store"] = "healthy" if vs._client else "mock_mode"
    except Exception:
        services["vector_store"] = "unavailable"
    services["llm"] = "configured" if settings.active_llm_api_key else "no_api_key"
    services["database"] = "configured" if "postgresql" in settings.database_url else "default"
    all_healthy = all(v in ("healthy", "configured", "mock_mode") for v in services.values())
    return HealthResponse(
        status="healthy" if all_healthy else "degraded", version="0.1.0",
        environment=settings.app_env.value, timestamp=datetime.utcnow(), services=services,
    )
