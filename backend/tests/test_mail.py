"""Mail tests. The important one is that the caller cannot choose the sender."""

from __future__ import annotations

import pytest

from app.config import settings
from app.services import mail as mail_service


def test_sender_is_forced_to_the_smtp_account():
    """A caller-supplied `from` must never become the envelope sender - otherwise
    this endpoint is an open relay."""
    message = mail_service._build_message(
        reply_to="attacker@evil.test",
        to="victim@example.com",
        subject="Hello",
        body="Body",
    )

    assert settings.smtp_user in message["From"]
    assert "evil.test" not in message["From"]
    assert message["Reply-To"] == "attacker@evil.test"


def test_reply_to_omitted_when_it_matches_the_account():
    message = mail_service._build_message(
        reply_to=settings.smtp_user, to="a@example.com", subject="S", body="B"
    )
    assert message["Reply-To"] is None


def test_send_requires_auth(client):
    response = client.post(
        "/api/mail/send",
        json={"from": "a@example.com", "to": "b@example.com", "subject": "S", "body": "B"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"from": "bad", "to": "b@example.com", "subject": "S", "body": "B"},
        {"from": "a@example.com", "to": "bad", "subject": "S", "body": "B"},
        {"from": "a@example.com", "to": "b@example.com", "subject": "", "body": "B"},
        {"from": "a@example.com", "to": "b@example.com", "subject": "S", "body": ""},
    ],
)
def test_send_rejects_bad_payloads(client, admin, payload):
    assert client.post("/api/mail/send", json=payload, headers=admin).status_code == 400


def test_delivered_mail_is_recorded_and_listed(client, monkeypatch, admin):
    sent = {}

    def fake_send(reply_to, to, subject, body):
        sent.update(reply_to=reply_to, to=to, subject=subject, body=body)

    monkeypatch.setattr(mail_service, "send_email", fake_send)

    response = client.post(
        "/api/mail/send",
        json={
            "from": "me@example.com",
            "to": "them@example.com",
            "subject": "Hi",
            "body": "Hello there",
        },
        headers=admin,
    )
    assert response.status_code == 200
    assert sent["to"] == "them@example.com"

    # Logged under the real sending account, not the caller's claim.
    listed = client.get("/api/mail/sent").json()["data"]
    assert listed[0]["recipient"] == "them@example.com"
    assert listed[0]["sender"] == settings.smtp_user


def test_delivered_mail_still_succeeds_when_logging_fails(client, monkeypatch, admin):
    """The mail is already gone. A logging failure must not return an error that
    makes the caller send it a second time."""
    monkeypatch.setattr(mail_service, "send_email", lambda *a, **k: None)
    monkeypatch.setattr(mail_service, "connect", _raising_connect)

    response = client.post(
        "/api/mail/send",
        json={"from": "a@example.com", "to": "b@example.com", "subject": "S", "body": "B"},
        headers=admin,
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"] is None


def _raising_connect(*_args, **_kwargs):
    raise RuntimeError("database unavailable")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("STARTTLS", False), ("starttls", False), ("none", False), ("plain", False),
        ("SSL", True), ("ssl", True), ("smtps", True), ("implicit", True),
        ("true", True), ("false", False), ("1", True), ("0", False), ("", False),
    ],
)
def test_smtp_secure_understands_protocol_names(monkeypatch, raw, expected):
    """SMTP_SECURE=SSL used to read as false, which silently timed out on port 465
    instead of connecting."""
    from app import config

    monkeypatch.setenv("SMTP_SECURE", raw)
    assert config._smtp_secure(False) is expected
