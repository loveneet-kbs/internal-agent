"""Small in-process sliding-window rate limiter.

Adequate for a single-process deployment. Behind more than one worker, swap the
`_HITS` dict for Redis - the dependency signature stays the same.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from .errors import ApiError

_WINDOW_SECONDS = 60.0
_HITS: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_LOCK = threading.Lock()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(bucket: str, per_minute: int):
    """Build a FastAPI dependency limiting `bucket` to `per_minute` requests per IP."""

    def dependency(request: Request) -> None:
        key = (bucket, _client_key(request))
        now = time.monotonic()
        cutoff = now - _WINDOW_SECONDS

        with _LOCK:
            hits = _HITS[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= per_minute:
                retry_after = max(1, int(_WINDOW_SECONDS - (now - hits[0])))
                raise ApiError(
                    429, f"Too many requests. Please slow down and retry in {retry_after}s."
                )
            hits.append(now)

    return dependency


def reset() -> None:
    """Clear all counters. Used by the test suite."""
    with _LOCK:
        _HITS.clear()
