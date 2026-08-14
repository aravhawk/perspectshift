"""Security middleware: headers, body size, correlation IDs."""

from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store",
}


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    correlation_id: str,
    remediation: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": correlation_id,
                "retryable": False,
                "details": {},
                "remediation": remediation,
            }
        },
        headers={"X-Correlation-ID": correlation_id},
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = getattr(request.state, "correlation_id", None) or str(uuid4())
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                return _error_response(
                    status_code=400,
                    code="REQUEST_INVALID",
                    message="Invalid Content-Length",
                    correlation_id=correlation_id,
                )
            if length > self.max_bytes:
                return _error_response(
                    status_code=413,
                    code="REQUEST_TOO_LARGE",
                    message=f"Request body exceeds {self.max_bytes} bytes",
                    correlation_id=correlation_id,
                    remediation="Reduce request payload size",
                )
        return await call_next(request)
