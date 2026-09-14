from __future__ import annotations

from fastapi import APIRouter

from ..config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    return {
        "success": True,
        "status": "ok",
        "groqConfigured": settings.groq_configured,
        "authConfigured": settings.auth_configured,
        "smtpConfigured": settings.smtp_configured,
    }
