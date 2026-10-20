"""API key authentication and per-key rate limiting for the `/v1/*` routes (RF-10).

- The key travels in the `X-API-Key` header and is compared with `hmac.compare_digest`.
- Without a configured `API_KEY` the protected routes fail closed (503), never open.
- The limiter is a fixed window kept in memory: it is per process, so with N uvicorn workers
  a key gets up to N times the limit (ADR 004). Only authenticated keys are counted, so the
  table cannot be filled with arbitrary header values.
"""

import hashlib
import hmac
import math
import threading
import time
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from fundos_api.db import get_settings_from_app
from fundos_api.schemas import ErrorResponse

API_KEY_HEADER = "X-API-Key"

api_key_header = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    scheme_name="ApiKeyAuth",
    description="API key configured on the server through the `API_KEY` setting.",
)

# Error responses shared by every protected route, for the OpenAPI document.
AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid `X-API-Key`"},
    429: {
        "model": ErrorResponse,
        "description": "Rate limit exceeded; retry after `Retry-After` seconds",
        "headers": {
            "Retry-After": {
                "description": "Seconds until the current window ends",
                "schema": {"type": "integer"},
            }
        },
    },
    503: {"model": ErrorResponse, "description": "Warehouse unavailable or API key not configured"},
}


class RateLimiter:
    """Fixed-window counter per key, thread-safe, in process memory."""

    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Count one request; None when allowed, else the seconds until the window resets."""
        now = self._clock()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= self.window_seconds:
                start, count = now, 0
            if count >= self.limit:
                return max(1, math.ceil(start + self.window_seconds - now))
            self._windows[key] = (start, count + 1)
            return None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": API_KEY_HEADER},
    )


def require_api_key(
    request: Request, api_key: Annotated[str | None, Security(api_key_header)]
) -> None:
    """Dependency for every `/v1/*` route: 503 if unconfigured, 401 if wrong, 429 if over."""
    expected = get_settings_from_app(request).api_key
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key not configured on the server",
        )
    if not api_key:
        raise _unauthorized(f"missing {API_KEY_HEADER} header")
    if not hmac.compare_digest(api_key.encode(), expected.get_secret_value().encode()):
        raise _unauthorized("invalid API key")
    limiter: RateLimiter = request.app.state.rate_limiter
    retry_after = limiter.hit(hashlib.sha256(api_key.encode()).hexdigest())
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
