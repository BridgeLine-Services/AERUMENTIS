"""
Aerumentis — Main FastAPI Application
Entry point. Assembles all routers, middleware, and lifecycle hooks.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from aerumentis.api.exceptions import register_exception_handlers
from aerumentis.api.v1.auth import router as auth_router
from aerumentis.api.v1.chat import router as chat_router
from aerumentis.api.v1.documents import router as documents_router
from aerumentis.api.v1.health import router as health_router
from aerumentis.core.config import get_settings
from aerumentis.core.database import close_db, init_db
from aerumentis.core.logging import get_logger
from aerumentis.modules.knowledge.routers.knowledge import router as knowledge_router
from aerumentis.modules.maintenance.routers.maintenance import router as maintenance_router
from aerumentis.modules.operations.routers.operations import router as operations_router

settings = get_settings()
logger = get_logger("aerumentis.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("aerumentis_starting", env=settings.app_env.value, host=settings.app_host, port=settings.app_port)
    if settings.is_development:
        try:
            await init_db()
        except Exception as e:
            logger.warning("db_init_skipped", error=str(e))
    try:
        from aerumentis.services.vector_store import get_vector_store
        vs = get_vector_store()
        await vs.ensure_collection("maintenance_docs")
    except Exception as e:
        logger.warning("vector_store_init_skipped", error=str(e))
    logger.info("aerumentis_ready")
    yield
    logger.info("aerumentis_shutting_down")
    for closer_name, closer in [("db", close_db)]:
        try:
            await closer()
        except Exception:
            pass
    for svc_name, svc_getter in [
        ("vector_store", "aerumentis.services.vector_store:get_vector_store"),
        ("llm", "aerumentis.services.llm_service:get_llm_service"),
        ("embeddings", "aerumentis.services.embedding_service:get_embedding_service"),
    ]:
        try:
            module_path, func_name = svc_getter.split(":")
            import importlib
            mod = importlib.import_module(module_path)
            svc = getattr(mod, func_name)()
            await svc.close()
        except Exception:
            pass
    logger.info("aerumentis_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Aerumentis",
        description=(
            "AI-powered operational brain for airports, maintenance teams, and airlines.\n\n"
            "**Module 1**: Maintenance Documentation AI (RAG-powered) — Active\n"
            "**Module 2**: Aerospace Knowledge Brain (Phase 2)\n"
            "**Module 3**: Airport Ground Operations (Phase 3)\n\n"
            "## Authentication\n"
            "All protected endpoints require either a `Bearer` JWT token or an `X-API-Key` header.\n"
            "Register at `/api/v1/auth/register` to get a token, or create API keys at `/api/v1/auth/api-keys`."
        ),
        version="0.1.0", docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json", lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    register_exception_handlers(app)

    api_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_prefix)
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(documents_router, prefix=api_prefix)
    app.include_router(chat_router, prefix=api_prefix)
    app.include_router(maintenance_router, prefix=api_prefix)
    app.include_router(knowledge_router, prefix=api_prefix)
    app.include_router(operations_router, prefix=api_prefix)

    @app.get("/", tags=["root"])
    async def root():
        return {
            "name": "Aerumentis", "version": "0.1.0",
            "description": "AI-powered operational brain for airports, maintenance teams, and airlines.",
            "docs": "/docs", "health": "/api/v1/health",
            "modules": {
                "maintenance": "Module 1 — Active (Documentation AI + Troubleshooting + Manual Search)",
                "knowledge": "Module 2 — Phase 2 (stub)",
                "operations": "Module 3 — Phase 3 (stub)",
            },
        }
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("aerumentis.main:app", host=settings.app_host, port=settings.app_port,
                reload=settings.is_development, log_level=settings.app_log_level)
