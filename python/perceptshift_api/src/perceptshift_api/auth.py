"""Mutation authentication and constant-time token comparison."""

from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from perceptshift_api.config import Settings
from perceptshift_api.errors import ApiError


def constant_time_token_equals(expected: str, provided: str) -> bool:
    """Compare tokens in constant time without leaking length via early exit of hmac."""
    expected_bytes = expected.encode("utf-8")
    provided_bytes = provided.encode("utf-8")
    # Pad to equal length so compare_digest always runs full compare on same-sized buffers.
    max_len = max(len(expected_bytes), len(provided_bytes), 1)
    expected_padded = expected_bytes.ljust(max_len, b"\0")
    provided_padded = provided_bytes.ljust(max_len, b"\0")
    lengths_match = hmac.compare_digest(
        len(expected_bytes).to_bytes(4, "big"),
        len(provided_bytes).to_bytes(4, "big"),
    )
    contents_match = hmac.compare_digest(expected_padded, provided_padded)
    return bool(lengths_match and contents_match)


class MutationRateLimiter:
    """Simple sliding-window rate limiter for mutation endpoints."""

    def __init__(self, limit_per_minute: int) -> None:
        self._limit = max(1, limit_per_minute)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        window = 60.0
        with self._lock:
            bucket = self._events[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= self._limit:
                raise ApiError(
                    "RATE_LIMITED",
                    "Mutation rate limit exceeded",
                    status_code=429,
                    retryable=True,
                    remediation="Wait before retrying mutation requests",
                )
            bucket.append(now)


def extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()


def require_mutation_auth(request: Request, settings: Settings) -> str:
    """Require a valid mutation token. Raises ApiError on failure."""
    expected = settings.resolve_mutation_token()
    if not expected:
        raise ApiError(
            "MUTATIONS_DISABLED",
            "Mutation endpoints are disabled",
            status_code=403,
            remediation=(
                "Set PERCEPTSHIFT_API_MUTATION_TOKEN, PERCEPTSHIFT_API_MUTATION_TOKEN_FILE, "
                "or provide systemd credential perceptshift-api-token"
            ),
        )
    provided = extract_bearer_token(request)
    if provided is None:
        raise ApiError(
            "AUTH_REQUIRED",
            "Bearer token required for mutations",
            status_code=401,
            remediation="Provide Authorization: Bearer <token>",
        )
    if not constant_time_token_equals(expected, provided):
        # Consume a tiny comparable amount of work on mismatch path as well.
        secrets.compare_digest(provided[:64], provided[:64])
        raise ApiError(
            "AUTH_INVALID",
            "Invalid mutation token",
            status_code=401,
            remediation="Provide a valid mutation token",
        )
    return "operator"
