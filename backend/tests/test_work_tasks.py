"""Work tasks and the employee snapshot."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agent import tools as registry
from app.agent.service import run_agent
from app.errors import ApiError
from app.services import attendance as attendance_service
from app.services import customers as customer_service
from app.services import leave as leave_service
from app.services import notes as note_service
from app.services import snapshot as snapshot_service
from app.services import work_tasks as service


def iso(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def crew():
    lead = customer_service.create_customer(
        "Priya Singh", "priya@example.com", team="Design", title="Design Lead",
        joined_at="2021-03-15",
    )
    junior = customer_service.create_customer(
        "Sana Qureshi", "sana@example.com", team="Design", title="Product Designer"
    )

    # manager_id is not part of the editable field set (it is org structure, not a
    # profile edit), so the fixture wires it directly.
    from app.db import connect

    with connect() as conn:
        conn.execute(
            "UPDATE customers SET manager_id = ? WHERE id = ?", (lead["id"], junior["id"])
        )

    return {"lead": lead, "junior": customer_service.get_customer(junior["id"])}


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "typed,expected",
    [("critical", "urgent"), ("p1", "high"), ("normal", "medium"), ("minor", "low")],
)
def test_priority_aliases(typed, expected):
    assert service.normalise_priority(typed) == expected


@pytest.mark.parametrize(
    "typed,expected",
    [
        ("in progress", "in_progress"), ("started", "in_progress"), ("wip", "in_progress"),
        ("finished", "done"), ("complete", "done"), ("stuck", "blocked"),
        ("backlog", "todo"), ("dropped", "cancelled"),
    ],
)
def test_status_aliases(typed, expected):
    assert service.normalise_status(typed) == expected


def test_unknown_priority_is_rejected():
    with pytest.raises(ApiError):
        service.normalise_priority("spicy")


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def test_create_with_assignee_inherits_their_team(crew):
    task = service.create("Ship tokens", assignee_id=crew["lead"]["id"])
    assert task["team"] == "Design"
    assert task["assignee"] == "Priya Singh"
    assert task["status"] == "todo"


def test_create_needs_a_title():
    with pytest.raises(ApiError):
        service.create("   ")


def test_create_rejects_a_bad_due_date(crew):
    with pytest.raises(ApiError) as exc:
        service.create("X", due_date="next tuesday")
    assert "Could not read" in exc.value.message


def test_create_rejects_an_unknown_assignee():
    with pytest.raises(ApiError) as exc:
        service.create("X", assignee_id=9999)
    assert exc.value.status_code == 404


def test_completion_stamps_the_time_and_reopening_clears_it(crew):
    task = service.create("Ship tokens", assignee_id=crew["lead"]["id"])
    done = service.update(task["id"], {"status": "done"})
    assert done["completed_at"] is not None

    reopened = service.update(task["id"], {"status": "in_progress"})
    assert reopened["completed_at"] is None


def test_update_rejects_unknown_columns(crew):
    task = service.create("X")
    with pytest.raises(ApiError) as exc:
        service.update(task["id"], {"created_by": "someone"})
    assert "Cannot change" in exc.value.message


def test_overdue_is_computed_not_stored(crew):
    late = service.create("Late thing", due_date=iso(-3))
    future = service.create("Future thing", due_date=iso(10))

    assert service.get_task(late["id"])["overdue"] == 1
    assert service.get_task(future["id"])["overdue"] == 0

    # Completing it stops it being overdue.
    service.update(late["id"], {"status": "done"})
    assert service.get_task(late["id"])["overdue"] == 0


# --------------------------------------------------------------------------- #
# Listing and summary
# --------------------------------------------------------------------------- #
def test_filters(crew):
    service.create("A", assignee_id=crew["lead"]["id"], priority="urgent")
    service.create("B", assignee_id=crew["junior"]["id"], status="done")
    service.create("C", team="AI")

    assert len(service.list_tasks(assignee_id=crew["lead"]["id"])) == 1
    assert len(service.list_tasks(team="Design")) == 2
    assert len(service.list_tasks(priority="urgent")) == 1
    assert len(service.list_tasks(open_only=True)) == 2
    assert len(service.list_tasks(unassigned=True)) == 1


def test_ordering_puts_overdue_and_urgent_first(crew):
    service.create("Later", priority="low", due_date=iso(30))
    service.create("Overdue", priority="low", due_date=iso(-1))
    service.create("Urgent", priority="urgent", due_date=iso(20))

    titles = [t["title"] for t in service.list_tasks()]
    assert titles[0] == "Overdue"
    assert titles[1] == "Urgent"


def test_summary_counts(crew):
    service.create("A", assignee_id=crew["lead"]["id"], priority="urgent")
    service.create("B", assignee_id=crew["lead"]["id"], due_date=iso(-2))
    done = service.create("C", assignee_id=crew["lead"]["id"])
    service.update(done["id"], {"status": "done"})

    data = service.summary(assignee_id=crew["lead"]["id"])
    assert data["total"] == 3
    assert data["open"] == 2
    assert data["done"] == 1
    assert data["overdue"] == 1
    assert data["urgent_open"] == 1
    assert data["completion_rate"] == 33


# --------------------------------------------------------------------------- #
# Snapshot
# --------------------------------------------------------------------------- #
def test_snapshot_pulls_everything_together(crew):
    lead, junior = crew["lead"], crew["junior"]
    service.create("Open thing", assignee_id=junior["id"], due_date=iso(-1))
    leave_service.create_request(junior["id"], iso(10), iso(12), "annual", "Break")
    attendance_service.mark(junior["id"], "present")
    note_service.add_note(junior["id"], "Prefers async reviews.")

    snap = snapshot_service.build(junior["id"])

    assert snap["profile"]["name"] == "Sana Qureshi"
    assert snap["manager"]["name"] == "Priya Singh"
    assert snap["attendance"]["today"] == "present"
    assert snap["leave"]["pending_count"] == 1
    assert snap["tasks"]["open"] == 1
    assert snap["tasks"]["overdue"] == 1
    assert len(snap["notes"]) == 1


def test_snapshot_lists_direct_reports(crew):
    snap = snapshot_service.build(crew["lead"]["id"])
    assert [r["name"] for r in snap["direct_reports"]] == ["Sana Qureshi"]
    assert snap["manager"] is None


def test_snapshot_headline_is_readable(crew):
    service.create("A", assignee_id=crew["lead"]["id"], due_date=iso(-1))
    headline = snapshot_service.headline(snapshot_service.build(crew["lead"]["id"]))

    assert "Priya Singh" in headline
    assert "Design team" in headline
    assert "1 overdue" in headline


def test_snapshot_of_a_missing_person():
    with pytest.raises(ApiError) as exc:
        snapshot_service.build(9999)
    assert exc.value.status_code == 404


def test_tenure_is_computed(crew):
    snap = snapshot_service.build(crew["lead"]["id"])
    assert snap["profile"]["tenure"] is not None


# --------------------------------------------------------------------------- #
# Through the agent
# --------------------------------------------------------------------------- #
def test_agent_creates_and_assigns_in_one_call(stub_model, crew):
    stub_model(
        "create_task",
        {
            "title": "Write the runbook",
            "assignee_name": "Priya Singh",
            "priority": "high",
            "due_date": iso(14),
        },
    )
    outcome = run_agent("create a task to write the runbook for Priya, high priority")

    assert outcome["success"] is True
    tasks = service.list_tasks(assignee_id=crew["lead"]["id"])
    assert tasks[0]["title"] == "Write the runbook"
    assert tasks[0]["priority"] == "high"


def test_agent_completes_a_task(stub_model, crew):
    task = service.create("Ship it", assignee_id=crew["lead"]["id"])
    stub_model("complete_task", {"task_id": task["id"], "note": "Shipped"})
    outcome = run_agent("mark that done")

    assert outcome["success"] is True
    assert service.get_task(task["id"])["status"] == "done"


def test_completing_twice_is_refused(stub_model, crew):
    task = service.create("Ship it")
    service.update(task["id"], {"status": "done"})

    stub_model("complete_task", {"task_id": task["id"]})
    outcome = run_agent("complete it")

    assert outcome["success"] is False
    assert "already completed" in outcome["task"]["error"]


def test_agent_snapshot_is_one_call(stub_model, crew):
    """The whole point: one tool, not six."""
    stub_model("employee_snapshot", {"match_name": "Sana Qureshi"})
    outcome = run_agent("tell me about Sana")

    assert outcome["success"] is True
    assert len(outcome["executed"]) == 1
    data = outcome["result"]["data"]
    assert {"profile", "manager", "attendance", "leave", "tasks", "notes"} <= set(data)


def test_agent_chains_task_then_email(stub_sequence, monkeypatch, crew):
    from app.services import drafting

    monkeypatch.setattr(
        drafting, "generate_draft", lambda **k: {"subject": "New task", "body": "Hi"}
    )
    stub_sequence(
        [
            ("create_task", {"title": "Audit contrast", "assignee_name": "Sana Qureshi"}),
            ("draft_email", {"recipient_name": "Sana Qureshi", "purpose": "new task"}),
        ]
    )
    outcome = run_agent("create a contrast audit task for Sana and email her")

    assert [s["tool"] for s in outcome["executed"]] == ["create_task", "draft_email"]


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def test_work_tasks_are_not_the_agent_history_route(client, crew):
    """/api/tasks is the agent's own runs; work lives at /api/work-tasks."""
    service.create("Distinct", assignee_id=crew["lead"]["id"])

    work = client.get("/api/work-tasks").json()["data"]
    history = client.get("/api/tasks").json()["data"]

    assert work[0]["title"] == "Distinct"
    assert all("title" not in row for row in history)


def test_creating_requires_auth(client):
    assert client.post("/api/work-tasks", json={"title": "X"}).status_code == 401


def test_crud_over_http(client, admin, crew):
    created = client.post(
        "/api/work-tasks",
        json={"title": "Ship it", "assignee_id": crew["lead"]["id"], "priority": "high"},
        headers=admin,
    )
    assert created.status_code == 201
    task_id = created.json()["data"]["id"]

    assert client.get(f"/api/work-tasks/{task_id}").status_code == 200
    assert client.post(f"/api/work-tasks/{task_id}/complete", headers=admin).status_code == 200
    assert client.post(f"/api/work-tasks/{task_id}/complete", headers=admin).status_code == 409


def test_summary_route_is_not_parsed_as_an_id(client, crew):
    assert client.get("/api/work-tasks/summary").status_code == 200


def test_snapshot_endpoint(client, crew):
    body = client.get(f"/api/customers/{crew['junior']['id']}/snapshot").json()
    assert body["success"] is True
    assert body["data"]["manager"]["name"] == "Priya Singh"
    assert "Sana Qureshi" in body["message"]
