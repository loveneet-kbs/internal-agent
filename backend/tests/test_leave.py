"""Leave requests: listing, approving, rejecting, and the status side effect."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.agent.service import run_agent
from app.errors import ApiError
from app.services import customers as customer_service
from app.services import leave as service


def iso(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


@pytest.fixture
def team():
    priya = customer_service.create_customer(
        "Priya Singh", "priya@example.com", team="Design", title="Design Lead"
    )
    rahul = customer_service.create_customer(
        "Rahul Sharma", "rahul@example.com", team="AI", title="Head of AI"
    )
    return {
        "priya": priya,
        "rahul": rahul,
        # future leave, does not cover today
        "future": service.create_request(priya["id"], iso(14), iso(18), "annual", "Wedding"),
        # spans today
        "current": service.create_request(rahul["id"], iso(-1), iso(3), "sick", "Flu"),
    }


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #
def test_pending_are_listed_with_the_person_attached(team):
    rows = service.list_requests(status="pending")
    assert len(rows) == 2
    assert {r["person"] for r in rows} == {"Priya Singh", "Rahul Sharma"}
    assert rows[0]["team"] in {"Design", "AI"}


def test_filter_by_team_and_type(team):
    assert len(service.list_requests(team="Design")) == 1
    assert len(service.list_requests(leave_type="sick")) == 1


def test_unknown_status_is_rejected(team):
    with pytest.raises(ApiError):
        service.list_requests(status="maybe")


@pytest.mark.parametrize(
    "typed,expected",
    [("holiday", "annual"), ("PTO", "annual"), ("medical", "sick"), ("maternity", "parental")],
)
def test_leave_type_aliases(typed, expected):
    assert service.normalise_type(typed) == expected


def test_unknown_leave_type_is_rejected():
    with pytest.raises(ApiError):
        service.normalise_type("interpretive dance")


# --------------------------------------------------------------------------- #
# Deciding
# --------------------------------------------------------------------------- #
def test_approving_a_future_leave_does_not_change_status(team):
    outcome = service.decide(request_id=team["future"]["id"], approve=True)

    assert outcome["request"]["status"] == "approved"
    assert outcome["status_changed"] is False
    assert customer_service.get_customer(team["priya"]["id"])["status"] == "active"


def test_approving_a_current_leave_marks_the_person_on_leave(team):
    """The integration that makes this more than a status flip."""
    outcome = service.decide(request_id=team["current"]["id"], approve=True)

    assert outcome["status_changed"] is True
    assert customer_service.get_customer(team["rahul"]["id"])["status"] == "on_leave"
    # and the customer search agrees
    assert [p["name"] for p in customer_service.search(status="on_leave")] == ["Rahul Sharma"]


def test_rejecting_records_the_reason_and_leaves_status_alone(team):
    outcome = service.decide(
        request_id=team["current"]["id"], approve=False, note="Cannot cover the on-call"
    )

    assert outcome["request"]["status"] == "rejected"
    assert outcome["request"]["decision_note"] == "Cannot cover the on-call"
    assert outcome["status_changed"] is False
    assert customer_service.get_customer(team["rahul"]["id"])["status"] == "active"


def test_deciding_twice_is_refused(team):
    service.decide(request_id=team["future"]["id"], approve=True)
    with pytest.raises(ApiError) as exc:
        service.decide(request_id=team["future"]["id"], approve=True)
    assert "already approved" in exc.value.message


def test_resolving_by_person_when_there_is_exactly_one_pending(team):
    outcome = service.decide(customer_id=team["priya"]["id"], approve=True)
    assert outcome["request"]["id"] == team["future"]["id"]


def test_several_pending_requests_ask_which_one(team):
    service.create_request(team["priya"]["id"], iso(40), iso(44), "casual", "Break")

    with pytest.raises(ApiError) as exc:
        service.decide(customer_id=team["priya"]["id"], approve=True)
    assert "which one" in exc.value.message
    assert "#" in exc.value.message  # lists the IDs to choose from


def test_person_with_no_pending_requests(team):
    other = customer_service.create_customer("Solo Person", "solo@example.com")
    with pytest.raises(ApiError) as exc:
        service.decide(customer_id=other["id"], approve=True)
    assert "no pending leave" in exc.value.message


def test_end_before_start_is_refused(team):
    with pytest.raises(ApiError):
        service.create_request(team["priya"]["id"], iso(10), iso(5))


def test_working_days_skips_weekends():
    # 2026-09-14 is a Monday; Mon-Fri is five working days.
    assert service._working_days("2026-09-14", "2026-09-18") == 5
    # across a weekend: Fri + Mon
    assert service._working_days("2026-09-18", "2026-09-21") == 2


# --------------------------------------------------------------------------- #
# Through the agent
# --------------------------------------------------------------------------- #
def test_agent_approves_by_name(stub_model, team):
    stub_model("approve_leave", {"match_name": "Priya Singh"})
    outcome = run_agent("approve Priya's leave")

    assert outcome["success"] is True
    assert service.get_request(team["future"]["id"])["status"] == "approved"


def test_agent_reject_requires_a_reason(stub_model, team):
    stub_model("reject_leave", {"match_name": "Priya Singh"})  # note missing
    outcome = run_agent("reject Priya's leave")

    assert outcome["success"] is False
    assert "Invalid arguments" in outcome["task"]["error"]
    assert service.get_request(team["future"]["id"])["status"] == "pending"


def test_agent_chains_approve_then_draft(stub_sequence, monkeypatch, team):
    """The composition that matters: decide, then tell them."""
    from app.services import drafting

    monkeypatch.setattr(
        drafting, "generate_draft", lambda **k: {"subject": "Leave approved", "body": "Hi"}
    )
    stub_sequence(
        [
            ("approve_leave", {"match_name": "Priya Singh"}),
            ("draft_email", {"recipient_name": "Priya Singh", "purpose": "leave approved"}),
        ]
    )
    outcome = run_agent("approve Priya's leave and email her")

    assert [step["tool"] for step in outcome["executed"]] == ["approve_leave", "draft_email"]
    assert service.get_request(team["future"]["id"])["status"] == "approved"
    assert outcome["result"]["data"]["kind"] == "email_draft"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def test_leave_endpoints_require_auth_to_decide(client, team):
    assert client.post(f"/api/leave/{team['future']['id']}/approve").status_code == 401
    assert (
        client.post(f"/api/leave/{team['future']['id']}/reject", json={"note": "x"}).status_code
        == 401
    )


def test_listing_is_open_and_carries_a_summary(client, team):
    body = client.get("/api/leave").json()
    assert body["success"] is True
    assert body["summary"]["pending"] == 2


def test_approve_over_http(client, admin, team):
    response = client.post(f"/api/leave/{team['current']['id']}/approve", headers=admin)
    assert response.status_code == 200
    assert "Marked on leave" in response.json()["message"]


def test_reject_over_http_needs_a_reason(client, admin, team):
    blank = client.post(
        f"/api/leave/{team['future']['id']}/reject", json={"note": "  "}, headers=admin
    )
    assert blank.status_code == 400

    ok = client.post(
        f"/api/leave/{team['future']['id']}/reject", json={"note": "No cover"}, headers=admin
    )
    assert ok.status_code == 200


def test_deciding_two_people_needs_no_lookup_first(stub_sequence, team):
    """The decide tools resolve by name, so a get_leave_requests pre-check is
    wasted work - and each extra LLM turn costs a round trip under rate limits."""
    # Rahul already has exactly one pending request from the fixture; adding a
    # second would (correctly) make match_name ambiguous.
    stub_sequence(
        [
            ("reject_leave", {"match_name": "Priya Singh", "note": "Not enough leave left"}),
            ("approve_leave", {"match_name": "Rahul Sharma"}),
        ]
    )
    outcome = run_agent("reject Priya's leave, not enough balance, and approve Rahul's")

    assert outcome["success"] is True
    assert [s["tool"] for s in outcome["executed"]] == ["reject_leave", "approve_leave"]
    assert service.get_request(team["future"]["id"])["status"] == "rejected"


def test_prompt_reserves_unsupported_for_out_of_scope():
    """"Nothing is pending" is a valid request that failed, not an unsupported one."""
    from app.agent.graph import SYSTEM_PROMPT

    prompt = " ".join(SYSTEM_PROMPT.split())
    # "nothing found" is a valid answer, not an unsupported request.
    assert "nothing found" in prompt
    # And the decide tools are called straight off, without a lookup first.
    assert "no lookup first" in prompt
