from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ErrorCode
from app.core.logging import logger


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "req_" + uuid.uuid4().hex[:12]


def ok(request: Request, data: Any = None) -> dict:
    return {"success": True, "data": data, "request_id": _request_id(request)}


def error(request: Request, code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {"code": code, "message": message},
        "request_id": _request_id(request),
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error(request, exc.code.value, exc.message))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error(request, "VALIDATION_ERROR", str(exc.errors())),
    )


def _code_for_status(status_code: int) -> str:
    """Map a bare HTTP status onto a member of the §77 error vocabulary."""
    return {
        401: ErrorCode.AUTH_UNAUTHORIZED.value,
        403: ErrorCode.TOOL_PERMISSION_DENIED.value,
        404: ErrorCode.RESOURCE_NOT_FOUND.value,
        422: ErrorCode.VALIDATION_ERROR.value,
    }.get(status_code, ErrorCode.INTERNAL_ERROR.value if status_code >= 500 else ErrorCode.VALIDATION_ERROR.value)


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Wrap framework-raised HTTPExceptions in the §76 response envelope.

    Without this, every ``raise HTTPException(...)`` (auth failures, 404s from
    route helpers) escapes as FastAPI's ``{"detail": ...}`` shape and breaks
    the single-envelope contract the frontend depends on.
    """
    code = _code_for_status(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error(request, code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def send_500_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the real cause server-side, but never leak internal exception text
    # (stack fragments, SQL, file paths) to the client.
    logger.error("unhandled_exception", error=str(exc), request_id=_request_id(request))
    return JSONResponse(status_code=500, content=error(request, "INTERNAL_ERROR", "Internal server error"))


def setup_exception_handlers(app: FastAPI) -> None:
    from app.core.errors import AppError

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, send_500_handler)
