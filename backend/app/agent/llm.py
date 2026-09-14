"""Lazy Groq client.

Built on first use, not at import time. The previous Node backend constructed the
client at module load, and the SDK throws on a missing key - so the process died at
boot with a stack trace instead of reaching its own "GROQ_API_KEY is not set" warning.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_groq import ChatGroq

from ..config import settings
from ..errors import ApiError


@lru_cache(maxsize=4)
def _build(model: str, temperature: float) -> ChatGroq:
    return ChatGroq(
        model=model,
        temperature=temperature,
        api_key=settings.groq_api_key,
        max_retries=2,
        timeout=45.0,
    )


def get_llm(temperature: float = 0.0) -> ChatGroq:
    if not settings.groq_configured:
        raise ApiError(
            503,
            "The AI service is not configured. Set GROQ_API_KEY in backend-python/.env.",
        )
    return _build(settings.groq_model, temperature)
