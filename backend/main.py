from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.config import Settings
from backend.core.database import build_engine, build_session_factory
from backend.core.errors import ApiError
from backend.core.models import Base
from backend.modules.identity.router import router as identity_router


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "error_type"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        return json.dumps(entry, separators=(",", ":"), ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True


logger = logging.getLogger("worldweave")


def create_app(
    settings: Settings | None = None,
    engine: Any | None = None,
) -> FastAPI:
    app_settings = settings or Settings.from_env()
    if app_settings.session_ttl_days < 1:
        raise ValueError("SESSION_TTL_DAYS must be positive")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        database_engine = engine or build_engine(app_settings.database_url)
        application.state.database_engine = database_engine
        application.state.session_factory = build_session_factory(database_engine)
        yield
        if engine is None:
            database_engine.dispose()

    app = FastAPI(
        title="WORLDWEAVE API",
        version="1.0.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.include_router(identity_router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": getattr(request.state, "request_id", "unavailable"),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_details = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "code": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": {"fields": safe_details},
                    "request_id": getattr(request.state, "request_id", "unavailable"),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content={
                "error": {
                    "code": "not_found" if exc.status_code == 404 else "http_error",
                    "message": "Resource not found."
                    if exc.status_code == 404
                    else "Request could not be completed.",
                    "details": {},
                    "request_id": getattr(request.state, "request_id", "unavailable"),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unavailable")
        logger.error(
            "unhandled_exception",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                    "details": {},
                    "request_id": request_id,
                }
            },
        )

    @app.get("/api/healthz", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api/readyz", tags=["health"])
    def readiness_check(request: Request) -> JSONResponse:
        session_factory = getattr(request.app.state, "session_factory", None)
        if session_factory is None:
            raise ApiError(503, "not_ready", "A required service is not ready.")
        try:
            with session_factory() as session:
                session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning(
                "readiness_failed",
                extra={"request_id": request.state.request_id, "error_type": type(exc).__name__},
            )
            raise ApiError(
                503, "not_ready", "A required service is not ready."
            ) from exc
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "checks": {"database": "ready"}},
        )

    return app


configure_logging()
app = create_app()
