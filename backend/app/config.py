"""Environment configuration, loaded and validated once at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from None


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# SMTP_SECURE means "connect with implicit SSL" (port 465) rather than plain
# SMTP plus STARTTLS (port 587). People naturally write the protocol name there
# instead of a boolean, and a bare truthiness check reads "SSL" as false - which
# silently produces a connection timeout on 465. Map the real words instead.
_SSL_WORDS = {"ssl", "smtps", "implicit", "tls"}
_STARTTLS_WORDS = {"starttls", "start_tls", "start-tls", "explicit", "none", "plain"}


def _smtp_secure(default: bool = False) -> bool:
    raw = os.getenv("SMTP_SECURE", "").strip().lower()
    if not raw:
        return default
    if raw in _SSL_WORDS:
        return True
    if raw in _STARTTLS_WORDS:
        return False
    return raw in {"1", "true", "yes", "on"}


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    port: int
    database_path: Path
    frontend_origins: tuple[str, ...]

    admin_token: str
    groq_api_key: str
    groq_model: str

    smtp_host: str
    smtp_port: int
    smtp_secure: bool
    smtp_user: str
    smtp_pass: str
    mail_sender_name: str

    max_prompt_chars: int
    max_body_bytes: int
    agent_rate_per_min: int
    mail_rate_per_min: int
    customer_rate_per_min: int

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def auth_configured(self) -> bool:
        return bool(self.admin_token)

    @property
    def smtp_configured(self) -> bool:
        return all([self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_pass])

    def missing_smtp_keys(self) -> list[str]:
        pairs = {
            "SMTP_HOST": self.smtp_host,
            "SMTP_PORT": self.smtp_port,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASS": self.smtp_pass,
        }
        return [key for key, value in pairs.items() if not value]


def _resolve_db_path(raw: str) -> Path:
    path = Path(raw or "./database/app.db")
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _resolve_origins(raw: str) -> tuple[str, ...]:
    # Unset -> sensible dev default. Explicitly empty -> no origins allowed.
    # Never "*": that combined with a bearer token is how CSRF-style abuse starts.
    if "FRONTEND_ORIGIN" not in os.environ:
        return ("http://localhost:3000", "http://127.0.0.1:3000")
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def load_settings() -> Settings:
    return Settings(
        port=_int("PORT", 8000),
        database_path=_resolve_db_path(_str("DATABASE_PATH")),
        frontend_origins=_resolve_origins(_str("FRONTEND_ORIGIN")),
        admin_token=_str("ADMIN_TOKEN"),
        groq_api_key=_str("GROQ_API_KEY"),
        groq_model=_str("GROQ_MODEL", "openai/gpt-oss-120b") or "openai/gpt-oss-120b",
        smtp_host=_str("SMTP_HOST"),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_secure=_smtp_secure(False),
        smtp_user=_str("SMTP_USER"),
        smtp_pass=os.getenv("SMTP_PASS", ""),
        mail_sender_name=_str("MAIL_SENDER_NAME", "Regina Grane") or "Regina Grane",
        max_prompt_chars=_int("MAX_PROMPT_CHARS", 2000),
        max_body_bytes=_int("MAX_BODY_BYTES", 32 * 1024),
        agent_rate_per_min=_int("AGENT_RATE_PER_MIN", 20),
        mail_rate_per_min=_int("MAIL_RATE_PER_MIN", 10),
        customer_rate_per_min=_int("CUSTOMER_RATE_PER_MIN", 60),
    )


settings = load_settings()
