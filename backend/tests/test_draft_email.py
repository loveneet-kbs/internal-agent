"""The draft-then-approve email flow.

The model is stubbed at both layers: the tool-selection call and the drafting call.
"""

from __future__ import annotations

import pytest

from app.agent.service import run_agent
from app.services import drafting

DRAFT = {"subject": "Project delay", "body": "Hi Rahul,\n\nWe slipped two weeks.\n\nThanks"}


@pytest.fixture
def stub_draft(monkeypatch):
    """Return a canned draft instead of calling the LLM."""
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return dict(DRAFT)

    monkeypatch.setattr(drafting, "generate_draft", fake)
    return calls


@pytest.fixture
def stub_selection(stub_model):
    """Force selection of draft_email with the given arguments."""

    def _install(args):
        stub_model("draft_email", args)

    return _install


def test_name_is_resolved_to_an_address(stub_selection, stub_draft, seeded):
    stub_selection({"recipient_name": "Rahul Sharma", "purpose": "project delay"})
    outcome = run_agent("Email Rahul Sharma about the project delay")

    assert outcome["success"] is True
    data = outcome["result"]["data"]
    assert data["kind"] == "email_draft"
    assert data["requires_approval"] is True
    assert data["to"] == "rahul@example.com"
    assert data["to_name"] == "Rahul Sharma"
    assert data["subject"] == DRAFT["subject"]


def test_prompt_forbids_asking_for_a_known_address():
    """Regression guard. The model used to call request_clarification asking for an
    email address it could have looked up from the name, because rule 3 ("never
    invent an email address") read as "always ask". Both halves of the correction
    must stay in the prompt."""
    from app.agent.graph import SYSTEM_PROMPT
    from app.agent.tools import REGISTRY

    def tool_description(name: str) -> str:
        return " ".join(REGISTRY[name].description.split())

    prompt = " ".join(SYSTEM_PROMPT.split())  # ignore line wrapping

    # Passing a name is not inventing, and the address is never asked for.
    assert "tools resolve names themselves" in prompt
    assert "never ask for an address" in tool_description("draft_email")


def test_direct_address_skips_the_lookup(stub_selection, stub_draft):
    stub_selection({"recipient_email": "someone@elsewhere.com", "purpose": "hello"})
    outcome = run_agent("Email someone@elsewhere.com to say hello")

    assert outcome["result"]["data"]["to"] == "someone@elsewhere.com"


def test_details_are_passed_through_to_the_writer(stub_selection, stub_draft, seeded):
    stub_selection(
        {
            "recipient_name": "Rahul Sharma",
            "purpose": "project delay",
            "details": "New deadline is 15 September.",
            "tone": "formal",
        }
    )
    run_agent("Tell Rahul the new deadline is 15 September")

    assert stub_draft[0]["details"] == "New deadline is 15 September."
    assert stub_draft[0]["tone"] == "formal"


def test_unknown_recipient_fails_before_drafting(stub_selection, stub_draft, seeded):
    stub_selection({"recipient_name": "Nobody Here", "purpose": "hello"})
    outcome = run_agent("Email Nobody Here")

    assert outcome["success"] is False
    assert "No customer found" in outcome["task"]["error"]
    assert stub_draft == []  # never reached the LLM


def test_ambiguous_recipient_refuses(stub_selection, stub_draft, seeded):
    """Two customers named Priya - pick neither."""
    stub_selection({"recipient_name": "Priya", "purpose": "hello"})
    outcome = run_agent("Email Priya")

    assert outcome["success"] is False
    assert "Multiple customers match" in outcome["task"]["error"]
    assert stub_draft == []


def test_missing_recipient_is_refused(stub_selection, stub_draft):
    stub_selection({"purpose": "hello"})
    outcome = run_agent("Send an email")

    assert outcome["success"] is False
    assert "Who should this email go to" in outcome["task"]["error"]


def test_malformed_address_is_refused(stub_selection, stub_draft):
    stub_selection({"recipient_email": "not-an-address", "purpose": "hello"})
    outcome = run_agent("Email not-an-address")

    assert outcome["success"] is False
    assert "not a valid email address" in outcome["task"]["error"]
    assert stub_draft == []


def test_drafting_never_sends(stub_selection, stub_draft, seeded, monkeypatch):
    """The whole point of the approval step."""
    sent = []
    from app.services import mail as mail_service

    monkeypatch.setattr(mail_service, "send_email", lambda *a, **k: sent.append(a))

    stub_selection({"recipient_name": "Rahul Sharma", "purpose": "hello"})
    run_agent("Email Rahul Sharma")

    assert sent == []
    from app.services import mail as service

    assert service.list_sent() == []


def test_approving_the_draft_sends_it(client, admin, monkeypatch, stub_selection, stub_draft, seeded):
    """Second half of the flow: the UI posts the approved draft to /api/mail/send."""
    from app.services import mail as mail_service

    delivered = {}
    monkeypatch.setattr(
        mail_service,
        "send_email",
        lambda reply_to, to, subject, body: delivered.update(to=to, subject=subject, body=body),
    )

    stub_selection({"recipient_name": "Rahul Sharma", "purpose": "project delay"})
    draft = run_agent("Email Rahul Sharma")["result"]["data"]

    response = client.post(
        "/api/mail/send",
        json={"to": draft["to"], "subject": draft["subject"], "body": draft["body"]},
        headers=admin,
    )

    assert response.status_code == 200
    assert delivered["to"] == "rahul@example.com"
    assert delivered["subject"] == DRAFT["subject"]
    assert client.get("/api/mail/sent").json()["data"][0]["recipient"] == "rahul@example.com"


def test_sending_still_requires_auth(client):
    """A draft in hand must not let an unauthenticated caller deliver it."""
    response = client.post(
        "/api/mail/send", json={"to": "a@example.com", "subject": "S", "body": "B"}
    )
    assert response.status_code == 401


def test_from_is_optional(client, admin, monkeypatch):
    """The approval card sends no `from`; the account address is used."""
    from app.services import mail as mail_service

    monkeypatch.setattr(mail_service, "send_email", lambda *a, **k: None)
    response = client.post(
        "/api/mail/send",
        json={"to": "a@example.com", "subject": "S", "body": "B"},
        headers=admin,
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# Draft quality and the honesty guard
# --------------------------------------------------------------------------- #
def test_signoff_is_appended_when_the_model_forgets():
    from app.services.drafting import _ensure_signoff

    assert _ensure_signoff("Hi,\n\nBody.").endswith("Regina Grane")
    # Already signed - do not double up.
    already = "Hi,\n\nBody.\n\nBest regards,\nRegina Grane"
    assert _ensure_signoff(already).count("Regina Grane") == 1


def test_drafting_prompt_puts_honesty_above_length():
    """Pushing for longer emails made the model invent deadlines and prior
    conversations. The precedence rule and its specific bans must stay."""
    from app.services.drafting import SYSTEM_PROMPT

    prompt = " ".join(SYSTEM_PROMPT.split())

    assert "HONESTY OUTRANKS LENGTH" in prompt
    assert "WRITE A SHORTER EMAIL" in prompt
    for banned in ("deadline", "prior conversation", "as we discussed"):
        assert banned in prompt, f"lost the guard against inventing a {banned}"


def test_drafting_prompt_asks_for_analysis_first():
    from app.services.drafting import SYSTEM_PROMPT

    assert "STAGE 1 - ANALYSE" in SYSTEM_PROMPT
    assert '"analysis"' in SYSTEM_PROMPT
    # analysis is reasoning scaffolding, never surfaced
    assert "discarded" in SYSTEM_PROMPT


def test_analysis_field_is_not_returned(monkeypatch):
    """The model returns analysis to think with; it must not leak into the draft."""
    import json

    from app.services import drafting

    class Reply:
        content = json.dumps(
            {
                "analysis": "internal reasoning that must not escape",
                "subject": "S",
                "body": "Hi,\n\nBody.\n\nRegina Grane",
            }
        )

    monkeypatch.setattr(drafting, "get_llm", lambda **_: type("M", (), {"invoke": lambda s, m: Reply()})())
    draft = drafting.generate_draft(recipient="A", purpose="p")

    assert set(draft) == {"subject", "body"}
    assert "internal reasoning" not in draft["body"]


def test_sender_name_is_configurable(monkeypatch):
    from dataclasses import replace

    from app.services import drafting

    monkeypatch.setattr(drafting, "settings", replace(drafting.settings, mail_sender_name="Ada Byron"))
    assert drafting._ensure_signoff("Hi,\n\nBody.").endswith("Ada Byron")
