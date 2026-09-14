"""Attendance marking, reading, and the leave integration."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agent.service import run_agent
from app.errors import ApiError
from app.services import attendance as service
from app.services import customers as customer_service
from app.services import leave as leave_service


def iso(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def team():
    return {
        "priya": customer_service.create_customer(
            "Priya Singh", "priya@example.com", team="Design", title="Design Lead"
        ),
        "rahul": customer_service.create_customer(
            "Rahul Sharma", "rahul@example.com", team="AI", title="Head of AI"
        ),
        "sneha": customer_service.create_customer(
            "Sneha Kulkarni", "sneha@example.com", team="QA", title="QA Lead"
        ),
    }


# --------------------------------------------------------------------------- #
# Status and date parsing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "typed,expected",
    [
        ("present", "present"), ("here", "present"), ("P", "present"),
        ("absent", "absent"), ("no show", "absent"), ("away", "absent"),
        ("leave", "leave"), ("off", "leave"), ("vacation", "leave"),
        ("half day", "half_day"), ("half-day", "half_day"),
        ("wfh", "wfh"), ("remote", "wfh"), ("work from home", "wfh"),
    ],
)
def test_status_aliases(typed, expected):
    assert service.normalise_status(typed) == expected


def test_unknown_status_is_rejected():
    with pytest.raises(ApiError):
        service.normalise_status("teleported")


def test_relative_dates():
    assert service.parse_day("today") == iso(0)
    assert service.parse_day("yesterday") == iso(-1)
    assert service.parse_day("2026-08-20") == "2026-08-20"
    # "this week" starts on Monday
    monday = date.today() - timedelta(days=date.today().weekday())
    assert service.parse_day("this week") == monday.isoformat()


def test_unparseable_date_is_rejected():
    with pytest.raises(ApiError) as exc:
        service.parse_day("next fortnight")
    assert "Could not read" in exc.value.message


# --------------------------------------------------------------------------- #
# Marking
# --------------------------------------------------------------------------- #
def test_mark_and_read_back(team):
    record = service.mark(team["priya"]["id"], "present")
    assert record["status"] == "present"
    assert record["person"] == "Priya Singh"
    assert record["day"] == iso(0)


def test_marking_the_same_day_twice_corrects_it(team):
    """One record per person per day - not a stack of duplicates."""
    service.mark(team["priya"]["id"], "present")
    service.mark(team["priya"]["id"], "absent")

    rows = service.list_records(customer_id=team["priya"]["id"])
    assert len(rows) == 1
    assert rows[0]["status"] == "absent"


def test_mark_a_past_day(team):
    record = service.mark(team["rahul"]["id"], "wfh", "yesterday")
    assert record["day"] == iso(-1)
    assert record["status"] == "wfh"


def test_marking_an_unknown_person_is_refused():
    with pytest.raises(ApiError) as exc:
        service.mark(9999, "present")
    assert exc.value.status_code == 404


def test_mark_many(team):
    ids = [p["id"] for p in team.values()]
    records = service.mark_many(ids, "present")
    assert len(records) == 3
    assert all(r["status"] == "present" for r in records)


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def test_filter_by_status_and_team(team):
    service.mark(team["priya"]["id"], "absent")
    service.mark(team["rahul"]["id"], "present")

    assert len(service.list_records(status="absent")) == 1
    assert len(service.list_records(team="Design")) == 1


def test_day_summary_counts_and_flags_the_unmarked(team):
    service.mark(team["priya"]["id"], "present")

    data = service.day_summary()
    assert data["present"] == 1
    assert data["headcount"] == 3
    assert data["unmarked"] == 2
    assert {p["name"] for p in data["unmarked_people"]} == {"Rahul Sharma", "Sneha Kulkarni"}


def test_person_summary_computes_a_rate(team):
    service.mark(team["priya"]["id"], "present", iso(-1))
    service.mark(team["priya"]["id"], "present", iso(-2))
    service.mark(team["priya"]["id"], "absent", iso(-3))

    data = service.person_summary(team["priya"]["id"])
    assert data["records"] == 3
    assert data["present"] == 2
    assert data["attendance_rate"] == 67


def test_working_days_skips_weekends():
    # 2026-09-14 Monday .. 2026-09-20 Sunday -> five weekdays
    assert len(service.working_days("2026-09-14", "2026-09-20")) == 5


# --------------------------------------------------------------------------- #
# Leave integration - the part that ties the two features together
# --------------------------------------------------------------------------- #
def test_approving_leave_writes_attendance_for_those_days(team):
    request = leave_service.create_request(
        team["rahul"]["id"], "2026-09-14", "2026-09-18", "annual", "Wedding"
    )
    outcome = leave_service.decide(request_id=request["id"], approve=True)

    assert outcome["attendance_days_marked"] == 5
    marked = service.list_records(customer_id=team["rahul"]["id"], status="leave")
    assert len(marked) == 5
    assert all(r["note"].startswith("Approved annual") for r in marked)


def test_rejecting_leave_writes_no_attendance(team):
    request = leave_service.create_request(team["rahul"]["id"], "2026-09-14", "2026-09-18")
    leave_service.decide(request_id=request["id"], approve=False, note="No cover")

    assert service.list_records(customer_id=team["rahul"]["id"]) == []


def test_approved_leave_skips_weekends(team):
    # Friday 2026-09-18 through Monday 2026-09-21
    request = leave_service.create_request(team["priya"]["id"], "2026-09-18", "2026-09-21")
    outcome = leave_service.decide(request_id=request["id"], approve=True)

    assert outcome["attendance_days_marked"] == 2


# --------------------------------------------------------------------------- #
# Through the agent
# --------------------------------------------------------------------------- #
def test_agent_marks_one_person(stub_model, team):
    stub_model("mark_attendance", {"match_name": "Priya Singh", "status": "absent"})
    outcome = run_agent("mark Priya absent")

    assert outcome["success"] is True
    assert service.list_records(customer_id=team["priya"]["id"])[0]["status"] == "absent"


def test_agent_marks_a_team(stub_model, team):
    stub_model("mark_bulk_attendance", {"team": "QA", "status": "present"})
    outcome = run_agent("mark the QA team present")

    assert outcome["success"] is True
    assert service.list_records(customer_id=team["sneha"]["id"])[0]["status"] == "present"


def test_agent_rejects_an_unknown_status(stub_model, team):
    stub_model("mark_attendance", {"match_name": "Priya Singh", "status": "teleported"})
    outcome = run_agent("mark Priya teleported")

    assert outcome["success"] is False
    assert "Unknown attendance status" in outcome["task"]["error"]


def test_agent_chains_attendance_then_email(stub_sequence, monkeypatch, team):
    from app.services import drafting

    monkeypatch.setattr(
        drafting, "generate_draft", lambda **k: {"subject": "Absence", "body": "Hi"}
    )
    stub_sequence(
        [
            ("mark_attendance", {"match_name": "Priya Singh", "status": "absent"}),
            ("draft_email", {"recipient_name": "Priya Singh", "purpose": "absence follow up"}),
        ]
    )
    outcome = run_agent("mark Priya absent and email her")

    assert [s["tool"] for s in outcome["executed"]] == ["mark_attendance", "draft_email"]
    assert service.list_records(customer_id=team["priya"]["id"])[0]["status"] == "absent"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def test_marking_requires_auth(client, team):
    response = client.post(
        "/api/attendance", json={"customer_id": team["priya"]["id"], "status": "present"}
    )
    assert response.status_code == 401


def test_mark_over_http(client, admin, team):
    response = client.post(
        "/api/attendance",
        json={"customer_id": team["priya"]["id"], "status": "wfh", "day": iso(-1)},
        headers=admin,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "wfh"


def test_listing_and_summary_are_open(client, team):
    service.mark(team["priya"]["id"], "present")
    assert client.get("/api/attendance").json()["data"]
    assert client.get("/api/attendance/summary").json()["data"]["present"] == 1


# --------------------------------------------------------------------------- #
# "everyone except X" - the case that silently did nothing
# --------------------------------------------------------------------------- #
def test_mark_everyone(team):
    from app.agent import tools as registry

    result = registry._mark_bulk_attendance(status="present", everyone=True)
    assert len(result["data"]) == 3
    assert "all active staff (3)" in result["message"]


def test_mark_everyone_leaves_people_already_on_leave_alone(team):
    """Marking someone on leave as present would overwrite a real fact."""
    from app.agent import tools as registry

    customer_service.update_customer(team["sneha"]["id"], {"status": "on_leave"})
    result = registry._mark_bulk_attendance(status="present", everyone=True)

    assert len(result["data"]) == 2
    assert "1 already on leave" in result["message"]
    assert service.list_records(customer_id=team["sneha"]["id"]) == []


def test_mark_everyone_except_one(team):
    from app.agent import tools as registry

    result = registry._mark_bulk_attendance(
        status="present", everyone=True, except_names=["Sneha Kulkarni"]
    )

    assert len(result["data"]) == 2
    assert "Skipped Sneha Kulkarni" in result["message"]
    # The excluded person is genuinely untouched, free to be marked differently.
    assert service.list_records(customer_id=team["sneha"]["id"]) == []


def test_bulk_requires_a_target(team):
    from app.agent import tools as registry

    with pytest.raises(ApiError) as exc:
        registry._mark_bulk_attendance(status="present")
    assert "everyone, a team, or a list" in exc.value.message


def test_excluding_everybody_is_refused(team):
    from app.agent import tools as registry

    with pytest.raises(ApiError) as exc:
        registry._mark_bulk_attendance(
            status="present",
            names=["Priya Singh"],
            except_names=["Priya Singh"],
        )
    assert "nobody to mark" in exc.value.message


def test_agent_marks_everyone_except_one(stub_sequence, team):
    """The reported bug: this used to list customers and finish without marking."""
    stub_sequence(
        [
            (
                "mark_bulk_attendance",
                {
                    "everyone": True,
                    "status": "present",
                    "except_names": ["Sneha Kulkarni"],
                },
            ),
            ("mark_attendance", {"match_name": "Sneha Kulkarni", "status": "absent"}),
        ]
    )
    outcome = run_agent("mark everyone present except Sneha Kulkarni who is absent")

    assert outcome["success"] is True
    assert service.list_records(customer_id=team["priya"]["id"])[0]["status"] == "present"
    assert service.list_records(customer_id=team["rahul"]["id"])[0]["status"] == "present"
    assert service.list_records(customer_id=team["sneha"]["id"])[0]["status"] == "absent"


def test_prompt_spells_out_the_everyone_except_pattern():
    """Regression guard: the model had no worked example and did nothing."""
    from app.agent.graph import SYSTEM_PROMPT

    prompt = " ".join(SYSTEM_PROMPT.split())
    assert "everyone=true" in prompt
    assert "except_names" in prompt
    # A change request must not be answered by reading alone.
    assert "must call a tool that changes it" in prompt


def test_both_bulk_tools_exist_and_do_not_overlap():
    """Team-scoped and everyone-scoped marking are separate tools on purpose."""
    from app.agent import tools as registry

    public = {tool["name"]: tool for tool in registry.list_public_tools()}
    assert "mark_team_attendance" in public
    assert "mark_bulk_attendance" in public

    # Descriptions must point the model at the right one.
    assert "everyone" in public["mark_bulk_attendance"]["description"].lower()
    assert "mark_bulk_attendance" in public["mark_team_attendance"]["description"]


def test_team_tool_still_marks_a_team(team):
    from app.agent import tools as registry

    result = registry._mark_team_attendance(status="present", team="QA")
    assert len(result["data"]) == 1
    assert service.list_records(customer_id=team["sneha"]["id"])[0]["status"] == "present"


def test_team_tool_marks_a_named_list(team):
    from app.agent import tools as registry

    result = registry._mark_team_attendance(
        status="wfh", names=["Priya Singh", "Rahul Sharma"]
    )
    assert len(result["data"]) == 2


def test_team_tool_requires_a_target(team):
    from app.agent import tools as registry

    with pytest.raises(ApiError) as exc:
        registry._mark_team_attendance(status="present")
    assert "team or a list of names" in exc.value.message


def test_agent_can_use_either_bulk_tool(stub_model, team):
    stub_model("mark_team_attendance", {"team": "QA", "status": "absent"})
    outcome = run_agent("mark QA absent")
    assert outcome["success"] is True
    assert service.list_records(customer_id=team["sneha"]["id"])[0]["status"] == "absent"
