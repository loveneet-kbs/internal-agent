"""SMTP delivery and the sent-mail log.

Security note: the envelope sender is ALWAYS the authenticated SMTP account.
The address the caller supplies becomes Reply-To. Without that, this endpoint is
an open relay that lets anyone send mail claiming to be anyone.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any

from ..config import settings
from ..db import connect
from ..errors import ApiError

log = logging.getLogger("app.mail")


def _require_smtp() -> None:
    missing = settings.missing_smtp_keys()
    if missing:
        raise ApiError(
            503,
            f"Email sending is not configured. Set {', '.join(missing)} in "
            "backend-python/.env before sending mail.",
        )

    # A port/TLS mismatch otherwise shows up as a connection timeout, which sends
    # you hunting for a network problem that isn't there.
    if settings.smtp_port == 465 and not settings.smtp_secure:
        raise ApiError(
            503,
            "Port 465 requires SMTP_SECURE=true (implicit SSL). Either set "
            "SMTP_SECURE=true, or use SMTP_PORT=587 with SMTP_SECURE=false.",
        )
    if settings.smtp_port == 587 and settings.smtp_secure:
        raise ApiError(
            503,
            "Port 587 requires SMTP_SECURE=false (STARTTLS). Either set "
            "SMTP_SECURE=false, or use SMTP_PORT=465 with SMTP_SECURE=true.",
        )


def _build_message(reply_to: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    # The From header matches the authenticated account so SPF/DKIM stay valid and
    # the API cannot be used to spoof a third party.
    message["From"] = formataddr((settings.mail_sender_name, settings.smtp_user))
    message["To"] = to
    message["Subject"] = subject
    if reply_to and parseaddr(reply_to)[1] != settings.smtp_user:
        message["Reply-To"] = reply_to
    message.set_content(body)
    return message


def send_email(reply_to: str, to: str, subject: str, body: str) -> None:
    _require_smtp()
    message = _build_message(reply_to, to, subject, body)

    try:
        if settings.smtp_secure:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=20, context=context
            ) as server:
                server.login(settings.smtp_user, settings.smtp_pass)
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(settings.smtp_user, settings.smtp_pass)
                server.send_message(message)

    except smtplib.SMTPAuthenticationError as exc:
        log.warning("SMTP auth failed for %s", settings.smtp_user)
        raise ApiError(
            502,
            "SMTP authentication failed. Check SMTP_USER and use a valid app password "
            "in backend-python/.env.",
        ) from exc
    except (smtplib.SMTPConnectError, OSError, TimeoutError) as exc:
        log.warning("SMTP connection failed: %s", exc)
        raise ApiError(
            502,
            "Could not connect to the SMTP server. Check SMTP_HOST, SMTP_PORT and "
            "SMTP_SECURE in backend-python/.env.",
        ) from exc
    except smtplib.SMTPException as exc:
        log.warning("SMTP rejected the message: %s", exc)
        raise ApiError(
            502, "The SMTP server rejected the email. Check your SMTP settings."
        ) from exc


def record_sent(sender: str, recipient: str, subject: str, body: str) -> dict[str, Any] | None:
    """Log a delivered message. Never raises: the mail is already gone, and failing
    the request here would make the caller send it a second time."""
    try:
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO sent_emails (sender, recipient, subject, body) VALUES (?, ?, ?, ?)",
                (sender, recipient, subject, body),
            )
            row = conn.execute(
                "SELECT * FROM sent_emails WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        log.exception("Delivered mail to %s but failed to record it", recipient)
        return None


def list_sent(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sent_emails ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(row) for row in rows]


def search_sent(
    recipient: str | None = None, contains: str | None = None, limit: int = 25
) -> list[dict[str, Any]]:
    """Search the sent log by recipient, or by text in the subject or body."""
    clauses, params = [], []
    esc = lambda v: v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")  # noqa: E731

    if recipient:
        clauses.append("recipient LIKE ? ESCAPE '\\' COLLATE NOCASE")
        params.append(f"%{esc(recipient)}%")
    if contains:
        clauses.append(
            "(subject LIKE ? ESCAPE '\\' COLLATE NOCASE OR body LIKE ? ESCAPE '\\' COLLATE NOCASE)"
        )
        params.extend([f"%{esc(contains)}%"] * 2)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT id, sender, recipient, subject, "
            f"substr(body, 1, 400) AS body, sent_at FROM sent_emails {where} "
            f"ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]
