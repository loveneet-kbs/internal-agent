"""Agent tests with a stubbed model, so the suite needs no API key and no network.

These cover the guardrail: what happens when the model picks a tool that does not
exist, or passes arguments that do not typecheck.
"""

from __future__ import annotations

from app.agent.service import run_agent

# `stub_model` comes from conftest.py.


def test_create_flows_through_to_the_database(stub_model):
    stub_model("create_customer", {"name": "Ada Lovelace", "email": "ada@example.com"})
    outcome = run_agent("Add Ada Lovelace with email ada@example.com")

    assert outcome["success"] is True
    assert outcome["task"]["status"] == "completed"
    assert outcome["task"]["tool_name"] == "create_customer"
    assert outcome["result"]["data"]["email"] == "ada@example.com"

    from app.services import customers as service

    assert len(service.find_by_name("Ada")) == 1


def test_unknown_tool_is_rejected_before_execution(stub_model):
    """The model naming something outside the registry must never execute."""
    stub_model("drop_all_tables", {})
    outcome = run_agent("do something dangerous")

    assert outcome["success"] is False
    assert outcome["task"]["status"] == "failed"
    assert "does not exist in the registry" in outcome["task"]["error"]


def test_bad_arguments_are_rejected_before_execution(stub_model):
    stub_model("get_customer", {"customer_id": "not-a-number"})
    outcome = run_agent("get customer banana")

    assert outcome["success"] is False
    assert outcome["task"]["status"] == "failed"
    assert "Invalid arguments" in outcome["task"]["error"]


def test_missing_required_argument_is_rejected(stub_model):
    stub_model("create_customer", {"name": "No Email"})
    outcome = run_agent("add someone")

    assert outcome["success"] is False
    assert "Invalid arguments" in outcome["task"]["error"]


def test_clarification_is_surfaced(stub_model):
    stub_model("request_clarification", {"question": "Which field should I change?"})
    outcome = run_agent("Update Rahul")

    assert outcome["success"] is False
    assert outcome["task"]["status"] == "needs_information"
    assert outcome["task"]["error"] == "Which field should I change?"


def test_unsupported_is_surfaced(stub_model):
    stub_model("report_unsupported", {"reason": "Weather is not customer data."})
    outcome = run_agent("What is the weather?")

    assert outcome["task"]["status"] == "unsupported"
    assert "Weather" in outcome["task"]["error"]


def test_ambiguous_name_asks_for_an_id(stub_model, seeded):
    """Two customers named Priya - the tool must refuse rather than pick one."""
    stub_model("delete_customer", {"match_name": "Priya"})
    outcome = run_agent("Delete Priya")

    assert outcome["success"] is False
    assert "Multiple customers match" in outcome["task"]["error"]

    from app.services import customers as service

    assert len(service.find_by_name("Priya")) == 2  # nothing was deleted


def test_rename_uses_match_name_and_new_name(stub_model, seeded):
    stub_model(
        "update_customer", {"match_name": "Rahul Sharma", "new_name": "Rahul S. Sharma"}
    )
    outcome = run_agent("Rename Rahul Sharma to Rahul S. Sharma")

    assert outcome["success"] is True
    assert outcome["result"]["data"]["name"] == "Rahul S. Sharma"


def test_update_with_no_new_values_is_refused(stub_model, seeded):
    stub_model("update_customer", {"match_name": "Rahul Sharma"})
    outcome = run_agent("Update Rahul Sharma")

    assert outcome["success"] is False
    assert "No new values" in outcome["task"]["error"]


def test_steps_are_recorded_for_the_ui(stub_model):
    stub_model("get_customers", {})
    outcome = run_agent("show everyone")

    labels = [step["label"] for step in outcome["steps"]]
    assert labels[0] == "Prompt received"
    assert "Task completed" in labels
    assert all(step["status"] != "running" for step in outcome["steps"])


def test_successful_run_is_logged_to_api_activity(stub_model):
    stub_model("get_customers", {})
    run_agent("show everyone")

    from app.services import tasks as service

    agent_rows = [row for row in service.recent_activity() if row["source"] == "agent"]
    assert agent_rows and agent_rows[0]["endpoint"] == "/api/customers"


def test_empty_generation_is_retried(monkeypatch):
    """Groq 400s with `tool_use_failed` when a forced tool call comes back empty.
    It is transient, so it must be retried rather than failing the task."""
    from app.agent import graph as agent_graph
    from tests.conftest import FakeModel, _call

    inner = FakeModel([[_call("get_customers", {})]])
    raised = {"n": 0}

    class FlakyModel(FakeModel):
        def __init__(self):
            super().__init__([])

        def invoke(self, messages):
            if raised["n"] == 0:
                raised["n"] += 1
                raise RuntimeError("Error code: 400 - {'error': {'code': 'tool_use_failed'}}")
            return inner.invoke(messages)

    monkeypatch.setattr(agent_graph, "get_llm", lambda **_: FlakyModel())
    outcome = run_agent("show everyone")

    assert raised["n"] == 1  # it did fail once
    assert outcome["success"] is True  # and recovered


def test_persistent_empty_generation_asks_for_a_rephrase(monkeypatch):
    from app.agent import graph as agent_graph

    class AlwaysEmpty:
        def bind_tools(self, *_a, **_k):
            return self

        def invoke(self, _messages):
            raise RuntimeError("Error code: 400 - {'error': {'code': 'tool_use_failed'}}")

    monkeypatch.setattr(agent_graph, "get_llm", lambda **_: AlwaysEmpty())
    outcome = run_agent("aaaaa")

    # A user-facing nudge, not a 500.
    assert outcome["task"]["status"] == "needs_information"
    assert "rephrasing" in outcome["task"]["error"]


def test_other_llm_errors_still_fail_the_task(monkeypatch):
    from app.agent import graph as agent_graph

    class Broken:
        def bind_tools(self, *_a, **_k):
            return self

        def invoke(self, _messages):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(agent_graph, "get_llm", lambda **_: Broken())
    outcome = run_agent("show everyone")

    assert outcome["success"] is False
    assert outcome["task"]["status"] == "failed"


def test_agent_route_rejects_an_overlong_prompt(client):
    response = client.post("/api/agent/run", json={"prompt": "x" * 5000})
    assert response.status_code == 400
    assert "limit is" in response.json()["error"]


def test_agent_route_rejects_an_empty_prompt(client):
    assert client.post("/api/agent/run", json={"prompt": "   "}).status_code == 400


def test_daily_quota_gives_an_actionable_message(monkeypatch):
    """A 429 quota ceiling must not be reported as 'could not be reached'."""
    from app.agent import graph as agent_graph

    class Throttled:
        def bind_tools(self, *_a, **_k):
            return self

        def invoke(self, _messages):
            raise RuntimeError(
                "Error code: 429 - {'error': {'message': 'Rate limit reached ... "
                "on tokens per day (TPD): Limit 200000'}}"
            )

    monkeypatch.setattr(agent_graph, "get_llm", lambda **_: Throttled())
    outcome = run_agent("show everyone")

    assert outcome["success"] is False
    assert "daily Groq token quota" in outcome["task"]["error"]


def test_transient_rate_limit_is_distinguished_from_the_daily_cap(monkeypatch):
    from app.agent import graph as agent_graph

    class Throttled:
        def bind_tools(self, *_a, **_k):
            return self

        def invoke(self, _messages):
            raise RuntimeError("Error code: 429 - rate_limit_exceeded, retry shortly")

    monkeypatch.setattr(agent_graph, "get_llm", lambda **_: Throttled())
    error = run_agent("show everyone")["task"]["error"]

    assert "rate limited right now" in error
    assert "daily" not in error


def test_quota_message_quotes_groqs_own_retry_time():
    """Groq says exactly how long to wait; guessing 'midnight' was wrong."""
    from app.agent.graph import _rate_limit_message

    message = _rate_limit_message(
        RuntimeError(
            "Error code: 429 - {'message': 'on tokens per day (TPD): Limit 200000. "
            "Please try again in 17m0.816s. Need more tokens?'}"
        )
    )
    assert "17m0.816s" in message
    assert ".." not in message  # the trailing period must not double up
