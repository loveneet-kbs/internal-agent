"""Admin-token auth for mutating routes.

Fails CLOSED: if ADMIN_TOKEN is not configured the route returns 503 rather than
waving the request through. The previous Node middleware did the opposite, which
meant an empty env var silently disabled all authentication.
"""

from __future__ import annotations

import secrets

from fastapi import Header

from .config import settings
from .errors import ApiError


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not settings.auth_configured:
        raise ApiError(
            503,
            "This route is disabled because ADMIN_TOKEN is not set. Add it to "
            "backend-python/.env (and VITE_ADMIN_TOKEN to frontend/.env) to enable it.",
        )

    expected = f"Bearer {settings.admin_token}"
    if not secrets.compare_digest(authorization or "", expected):
        raise ApiError(401, "Authentication required.")
