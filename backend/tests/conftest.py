"""Test fixtures.

Environment is pinned BEFORE anything under `app` is imported, so the suite never
picks up the developer's real .env, never talks to Groq, and never touches the real
database file.
"""

from __future__ import annotations

import os

os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["GROQ_API_KEY"] = "test-key-not-used"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:3000"
os.environ["SMTP_HOST"] = "smtp.example.com"
os.environ["SMTP_PORT"] = "587"
os.environ["SMTP_USER"] = "service@example.com"
os.environ["SMTP_PASS"] = "not-a-real-password"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app import db, ratelimit  # noqa: E402
from app.agent import graph as agent_graph  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_HEADERS = {"Authorization": "Bearer test-admin-token"}


class FakeModel:
    """Stands in for ChatGroq. Plays a scripted sequence of tool calls - one per
    turn - then replies with plain text, which is how the agent loop ends.

    `script` is a list of turns; each turn is a list of tool-call dicts.
    """

    def __init__(self, script):
        self._script = [list(turn) for turn in script]
        self.turns = 0

    def bind_tools(self, *_args, **_kwargs):
        return self

    def invoke(self, _messages):
        self.turns += 1
        if self._script:
            return AIMessage(content="", tool_calls=self._script.pop(0))
        return AIMessage(content="Done.")  # no tool call -> run finishes


def _call(name, args, index=1):
    return {"name": name, "args": args, "id": f"call_{index}", "type": "tool_call"}


@pytest.fixture
def stub_model(monkeypatch):
    """Force the agent to select one tool, then finish."""

    def _install(name, args):
        model = FakeModel([[_call(name, args)]])
        monkeypatch.setattr(agent_graph, "get_llm", lambda **_: model)
        return model

    return _install


@pytest.fixture
def stub_sequence(monkeypatch):
    """Script a multi-step run: [(tool, args), (tool, args), ...]."""

    def _install(steps):
        model = FakeModel([[_call(name, args, i)] for i, (name, args) in enumerate(steps, 1)])
        monkeypatch.setattr(agent_graph, "get_llm", lambda **_: model)
        return model

    return _install


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets an empty database and a clean rate-limit window."""
    monkeypatch.setattr(db, "_db_path", tmp_path / "test.db")
    db.init_database()
    ratelimit.reset()
    yield


@pytest.fixture
def client():
    # `with` runs the lifespan, matching production startup.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin():
    return ADMIN_HEADERS


@pytest.fixture
def seeded():
    """Three customers, returned as dicts."""
    from app.services import customers as service

    return [
        service.create_customer("Rahul Sharma", "rahul@example.com", "9876543210"),
        service.create_customer("Priya Singh", "priya@example.com", "9876511111"),
        service.create_customer("Priya Mehta", "priya.m@example.com", "9876522222"),
    ]
