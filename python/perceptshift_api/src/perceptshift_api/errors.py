"""Typed API error envelope."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Application error that maps to the documented envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        remediation: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}
        self.remediation = remediation
        self.correlation_id = correlation_id or str(uuid4())

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "correlation_id": self.correlation_id,
                "retryable": self.retryable,
                "details": self.details,
                "remediation": self.remediation,
            }
        }


def _correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None)
    if isinstance(existing, str) and existing:
        return existing
    header = request.headers.get("x-correlation-id")
    return header or str(uuid4())


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    if not exc.correlation_id:
        exc.correlation_id = _correlation_id(request)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        401: "AUTH_REQUIRED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        413: "REQUEST_TOO_LARGE",
        429: "RATE_LIMITED",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    details: dict[str, Any] = {}
    if not isinstance(detail, str) and detail is not None:
        details = {"detail": detail}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": _correlation_id(request),
                "retryable": exc.status_code in {408, 429, 503},
                "details": details,
                "remediation": None,
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "correlation_id": _correlation_id(request),
                "retryable": False,
                "details": {"issues": exc.errors()},
                "remediation": "Correct the request body or query parameters and retry",
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _ = exc
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "correlation_id": _correlation_id(request),
                "retryable": True,
                "details": {},
                "remediation": "Retry the request; if it persists, inspect API logs",
            }
        },
    )
