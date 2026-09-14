from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import get_database_path, init_database
from .errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from .routers import (
    agent,
    analytics,
    attendance,
    customers,
    health,
    leave,
    mail,
    meetings,
    tasks,
    work_tasks,
)
from .services import tasks as task_service

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("app")

# Endpoints that would otherwise log themselves on every poll.
ACTIVITY_EXCLUDE = {"/api/health", "/api/tasks/activity/recent"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    log.info("Database ready at %s", get_database_path())
    log.info("CORS origins: %s", ", ".join(settings.frontend_origins) or "(none)")

    if not settings.groq_configured:
        log.warning("GROQ_API_KEY is not set - /api/agent/run will return 503.")
    if not settings.auth_configured:
        log.warning(
            "ADMIN_TOKEN is not set - create/update/delete and mail send return 503. "
            "This is deliberate: auth fails closed."
        )
    if not settings.smtp_configured:
        log.info("SMTP is not fully configured - /api/mail/send will return 503.")

    try:
        yield
    finally:
        task_service.prune_activity()


app = FastAPI(
    title="AI Task Agent",
    description="LangGraph agent over a customer database, plus an AI mail composer.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Reject oversized bodies before they are parsed."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_body_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "success": False,
                "error": f"Request body exceeds {settings.max_body_bytes} bytes.",
            },
        )
    return await call_next(request)


@app.middleware("http")
async def record_activity(request: Request, call_next):
    """Log every real API call.

    The Node version only logged calls the agent made, so the UI's "API Activity"
    panel never showed the requests the UI itself was making.
    """
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)

    path = request.url.path
    if path.startswith("/api") and path not in ACTIVITY_EXCLUDE and request.method != "OPTIONS":
        try:
            task_service.log_activity(
                method=request.method,
                endpoint=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                source="http",
            )
        except Exception:  # noqa: BLE001 - logging must never break a response
            log.exception("Failed to record API activity for %s %s", request.method, path)

    return response


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(health.router)
app.include_router(customers.router)
app.include_router(tasks.router)
app.include_router(leave.router)
app.include_router(attendance.router)
app.include_router(work_tasks.router)
app.include_router(meetings.router)
app.include_router(analytics.router)
app.include_router(agent.router)
app.include_router(mail.router)


@app.get("/{path:path}", include_in_schema=False)
def not_found(path: str):
    return JSONResponse(status_code=404, content={"success": False, "error": "Route not found"})
