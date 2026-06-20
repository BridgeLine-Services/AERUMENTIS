"""Aerumentis — API Exception Handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aerumentis.core.logging import get_logger
from aerumentis.models.schemas import ErrorResponse

logger = get_logger("aerumentis.exceptions")


class AerumentisError(Exception):
    def __init__(self, message: str, detail: str | None = None, status_code: int = 500):
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AerumentisError):
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message, detail, 404)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AerumentisError)
    async def aerumentis_error_handler(request: Request, exc: AerumentisError):
        logger.warning("app_error", message=exc.message, status_code=exc.status_code, path=str(request.url))
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error=exc.message, detail=exc.detail, status_code=exc.status_code).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.error("unhandled_error", error=str(exc), error_type=type(exc).__name__, path=str(request.url))
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error="Internal server error", status_code=500).model_dump(),
        )
