"""Multi-step runs: several tools chained to satisfy one prompt."""

from __future__ import annotations

import pytest

from app.agent import graph as agent_graph
from app.agent.service import run_agent
from app.services import customers as customer_service
from app.services import drafting


@pytest.fixture
def stub_draft(monkeypatch):
    monkeypatch.setattr(
        drafting,
        "generate_draft",
        lambda **kwargs: {"subject": "Welcome", "body": "Hi,\n\nWelcome.\n\nRegina Grane"},
    )


def test_create_then_email_in_one_run(stub_sequence, stub_draft):
    """The headline case: 'add Aisha and send her a welcome email'."""
    stub_sequence(
        [
            ("create_customer", {"name": "Aisha Khan", "email": "aisha@example.com"}),
            ("draft_email", {"recipient_name": "Aisha Khan", "purpose": "welcome"}),
        ]
    )
    outcome = run_agent("Add Aisha Khan with email aisha@example.com and send her a welcome email")

    assert outcome["success"] is True
    assert [step["tool"] for step in outcome["executed"]] == ["create_customer", "draft_email"]

    # Both effects really happened.
    assert len(customer_service.find_by_name("Aisha")) == 1
    assert outcome["result"]["data"]["kind"] == "email_draft"
    assert outcome["result"]["data"]["to"] == "aisha@example.com"


def test_history_records_the_whole_chain(stub_sequence, stub_draft):
    stub_sequence(
        [
            ("create_customer", {"name": "Bo Lin", "email": "bo@example.com"}),
            ("draft_email", {"recipient_name": "Bo Lin", "purpose": "welcome"}),
        ]
    )
    task = run_agent("add Bo Lin and email them")["task"]

    assert task["tool_name"] == "create_customer, draft_email"
    assert isinstance(task["parameters"], list)
    assert len(task["parameters"]) == 2
    # method/endpoint track the final call
    assert task["endpoint"] == "/api/mail/generate"


def test_three_step_chain(stub_sequence, seeded):
    stub_sequence(
        [
            ("get_customers", {}),
            ("update_customer", {"match_name": "Rahul Sharma", "phone": "999"}),
            ("get_customer", {"customer_id": seeded[0]["id"]}),
        ]
    )
    outcome = run_agent("look everyone up, set Rahul's phone, then show me him")

    assert outcome["success"] is True
    assert len(outcome["executed"]) == 3
    assert customer_service.get_customer(seeded[0]["id"])["phone"] == "999"


def test_a_failing_step_stops_the_chain(stub_sequence, seeded):
    """A mid-chain failure must not silently continue to the next tool."""
    stub_sequence(
        [
            ("get_customers", {}),
            ("delete_customer", {"match_name": "Priya"}),  # ambiguous -> fails
            ("create_customer", {"name": "Should Not Run", "email": "no@example.com"}),
        ]
    )
    outcome = run_agent("list them, delete Priya, then add someone")

    assert outcome["success"] is False
    assert outcome["task"]["status"] == "failed"
    assert "Multiple customers match" in outcome["task"]["error"]
    assert len(outcome["executed"]) == 1  # only the successful first step
    assert customer_service.find_by_name("Should Not Run") == []


def test_step_cap_is_enforced(stub_sequence, monkeypatch):
    """A runaway loop is bounded."""
    monkeypatch.setattr(agent_graph, "MAX_STEPS", 3)
    stub_sequence([("get_customers", {}) for _ in range(10)])

    outcome = run_agent("keep going forever")

    assert len(outcome["executed"]) <= 3


def test_single_tool_runs_still_work(stub_model, seeded):
    """The common case must not regress now that the graph loops."""
    stub_model("get_customers", {})
    outcome = run_agent("show everyone")

    assert outcome["success"] is True
    assert len(outcome["executed"]) == 1
    assert len(outcome["result"]["data"]) == 3


def test_steps_trace_every_call(stub_sequence, stub_draft):
    stub_sequence(
        [
            ("create_customer", {"name": "Trace Me", "email": "trace@example.com"}),
            ("draft_email", {"recipient_name": "Trace Me", "purpose": "hello"}),
        ]
    )
    labels = [step["label"] for step in run_agent("add and email")["steps"]]

    assert labels[0] == "Prompt received"
    assert "Tool selected: create_customer" in labels
    assert "Tool selected: draft_email" in labels
    assert labels[-1] == "Task completed"


def test_clarification_still_ends_the_run(stub_model):
    stub_model("request_clarification", {"question": "Which field?"})
    outcome = run_agent("update someone")

    assert outcome["task"]["status"] == "needs_information"
    assert outcome["executed"] == []


def test_every_step_result_reaches_the_client(stub_sequence, stub_draft, seeded):
    """A chain like "who is on leave, then email X" returns a LIST and a DRAFT.
    Only the final result used to reach the UI, so the list was silently dropped."""
    stub_sequence(
        [
            ("search_customers", {"status": "active"}),
            ("draft_email", {"recipient_name": "Rahul Sharma", "purpose": "cover"}),
        ]
    )
    outcome = run_agent("who is active, then email Rahul to cover")

    assert len(outcome["executed"]) == 2

    first, second = outcome["executed"]
    assert first["tool"] == "search_customers"
    assert isinstance(first["result"]["data"], list) and first["result"]["data"]
    assert second["result"]["data"]["kind"] == "email_draft"

    # `result` still holds the final step, so existing callers keep working.
    assert outcome["result"]["data"]["kind"] == "email_draft"


def test_single_step_runs_still_carry_their_result(stub_model, seeded):
    stub_model("search_customers", {"team": "Design"})
    outcome = run_agent("show design")

    assert len(outcome["executed"]) == 1
    assert outcome["executed"][0]["result"] == outcome["result"]
