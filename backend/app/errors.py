"""Public-facing error type plus the handlers that keep internals out of responses."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class ApiError(Exception):
    """An error whose message is safe to show the caller."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _payload(message: str) -> dict:
    return {"success": False, "error": message}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_payload(exc.message))


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(status_code=exc.status_code, content=_payload(detail))


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
    message = first.get("msg", "Invalid request body.")
    return JSONResponse(
        status_code=400,
        content=_payload(f"{field}: {message}" if field else message),
    )


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Full detail to the server log, a generic line to the caller.
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_payload("Something went wrong while processing your request."),
    )
