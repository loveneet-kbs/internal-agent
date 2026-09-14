"""The profile fields, soft delete, notes, search and bulk tools."""

from __future__ import annotations

import pytest

from app.agent.service import run_agent
from app.errors import ApiError
from app.services import customers as service
from app.services import notes as note_service


@pytest.fixture
def staff():
    """A small cross-team set."""
    return [
        service.create_customer(
            "Priya Singh", "priya@example.com", "1", team="Design",
            title="Design Lead", location="Bengaluru", joined_at="2021-03-15",
        ),
        service.create_customer(
            "Rahul Sharma", "rahul@example.com", "2", team="AI",
            title="Head of AI", location="Bengaluru", joined_at="2020-08-03",
        ),
        service.create_customer(
            "Zoya Ansari", "zoya@example.com", "3", team="Development",
            title="Frontend Engineer", location="Hyderabad", joined_at="2024-04-18",
        ),
        service.create_customer(
            "Ritu Chauhan", "ritu@example.com", "4", team="Development",
            title="Mobile Engineer", location="Jaipur", status="alumni",
            joined_at="2021-02-08",
        ),
    ]


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def test_search_by_team(staff):
    assert {p["name"] for p in service.search(team="Development")} == {
        "Zoya Ansari",
        "Ritu Chauhan",
    }


def test_search_by_partial_title(staff):
    """'engineer' must match 'Frontend Engineer' and 'Mobile Engineer'."""
    assert len(service.search(title="engineer")) == 2


def test_search_combines_filters(staff):
    found = service.search(title="engineer", joined_after="2024-01-01")
    assert [p["name"] for p in found] == ["Zoya Ansari"]


def test_search_by_location_and_email(staff):
    assert len(service.search(location="bengaluru")) == 2
    assert len(service.search(email_contains="zoya@")) == 1


def test_search_rejects_an_unsafe_sort_column(staff):
    with pytest.raises(ApiError) as exc:
        service.search(sort="name; DROP TABLE customers")
    assert "Cannot sort by" in exc.value.message


def test_search_escapes_wildcards(staff):
    assert service.search(name="%") == []


@pytest.mark.parametrize("typed", ["on leave", "on-leave", "On Leave", "ONLEAVE"])
def test_status_aliases_normalise(typed):
    """The column stores `on_leave`; returning zero rows for "on leave" is a bug."""
    assert service.normalise_status(typed) == "on_leave"


def test_unknown_status_is_rejected():
    with pytest.raises(ApiError):
        service.normalise_status("wandering")


# --------------------------------------------------------------------------- #
# Soft delete and restore
# --------------------------------------------------------------------------- #
def test_delete_is_reversible(staff):
    target = staff[0]["id"]
    service.delete_customer(target)

    assert service.get_customer(target) is None          # hidden from reads
    assert service.count_customers() == 3
    assert [p["name"] for p in service.list_deleted()] == ["Priya Singh"]

    restored = service.restore_customer(target)
    assert restored["name"] == "Priya Singh"
    assert service.count_customers() == 4


def test_deleted_people_are_excluded_from_search(staff):
    service.delete_customer(staff[1]["id"])
    assert all(p["name"] != "Rahul Sharma" for p in service.search())


def test_restore_resolves_a_deleted_person_by_name(staff):
    """Undo is phrased by name, and the person is no longer in normal results."""
    service.delete_customer(staff[2]["id"])
    found = service.resolve_deleted(None, "Zoya")
    assert found["name"] == "Zoya Ansari"


def test_restoring_someone_not_deleted_is_refused(staff):
    with pytest.raises(ApiError) as exc:
        service.resolve_deleted(staff[0]["id"], None)
    assert "not deleted" in exc.value.message


def test_restore_agent_flow_by_name(stub_model, staff):
    service.delete_customer(staff[2]["id"])
    stub_model("restore_customer", {"match_name": "Zoya Ansari"})
    outcome = run_agent("undo that, restore Zoya Ansari")

    assert outcome["success"] is True
    assert service.get_customer(staff[2]["id"]) is not None


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
def test_notes_round_trip(staff):
    note_service.add_note(staff[0]["id"], "Prefers async reviews.")
    notes = note_service.list_notes(staff[0]["id"])
    assert notes[0]["body"] == "Prefers async reviews."


def test_note_on_a_missing_person_is_refused():
    with pytest.raises(ApiError) as exc:
        note_service.add_note(9999, "hello")
    assert exc.value.status_code == 404


def test_empty_note_is_refused(staff):
    with pytest.raises(ApiError):
        note_service.add_note(staff[0]["id"], "   ")


def test_add_note_via_agent_by_name(stub_model, staff):
    stub_model("add_note", {"match_name": "Rahul Sharma", "body": "Prefers mornings."})
    outcome = run_agent("note that Rahul prefers mornings")

    assert outcome["success"] is True
    assert note_service.list_notes(staff[1]["id"])[0]["body"] == "Prefers mornings."


# --------------------------------------------------------------------------- #
# Bulk create
# --------------------------------------------------------------------------- #
def test_bulk_create_reports_partial_failure(staff):
    outcome = service.create_many(
        [
            {"name": "Neil Arora", "email": "neil@example.com", "team": "Design"},
            {"name": "Dupe", "email": "priya@example.com"},  # already taken
            {"name": "Maya Rao", "email": "maya@example.com", "team": "AI"},
        ]
    )
    assert len(outcome["created"]) == 2
    assert len(outcome["skipped"]) == 1
    assert "already exists" in outcome["skipped"][0]["reason"]


def test_bulk_create_via_agent(stub_model):
    stub_model(
        "create_customers_bulk",
        {
            "people": [
                {"name": "A One", "email": "a1@example.com", "team": "Design"},
                {"name": "B Two", "email": "b2@example.com", "team": "AI"},
            ]
        },
    )
    outcome = run_agent("add A One and B Two")

    assert outcome["success"] is True
    assert service.count_customers() == 2


# --------------------------------------------------------------------------- #
# Stats
# --------------------------------------------------------------------------- #
def test_team_overview(staff):
    data = service.stats()
    assert data["total"] == 4
    assert data["alumni"] == 1
    teams = {t["team"]: t["headcount"] for t in data["teams"]}
    assert teams == {"Development": 2, "AI": 1, "Design": 1}


def test_stats_counts_the_recycle_bin_separately(staff):
    service.delete_customer(staff[0]["id"])
    data = service.stats()
    assert data["total"] == 3
    assert data["in_recycle_bin"] == 1


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #
def test_profile_endpoint_includes_notes(client, staff):
    note_service.add_note(staff[0]["id"], "Context.")
    body = client.get(f"/api/customers/{staff[0]['id']}").json()["data"]
    assert body["team"] == "Design"
    assert body["title"] == "Design Lead"
    assert len(body["notes"]) == 1


def test_search_endpoint(client, staff):
    rows = client.get("/api/customers/search?team=AI").json()["data"]
    assert [r["name"] for r in rows] == ["Rahul Sharma"]


def test_stats_endpoint(client, staff):
    assert client.get("/api/customers/stats").json()["data"]["total"] == 4


def test_restore_endpoint_requires_auth(client, staff):
    service.delete_customer(staff[0]["id"])
    assert client.post(f"/api/customers/{staff[0]['id']}/restore").status_code == 401


def test_delete_then_restore_over_http(client, admin, staff):
    target = staff[0]["id"]
    assert client.delete(f"/api/customers/{target}", headers=admin).status_code == 200
    assert client.get(f"/api/customers/{target}").status_code == 404
    assert client.post(f"/api/customers/{target}/restore", headers=admin).status_code == 200
    assert client.get(f"/api/customers/{target}").status_code == 200


def test_literal_routes_are_not_parsed_as_ids(client, staff):
    """/search and /stats must not be captured by /{customer_id}."""
    assert client.get("/api/customers/search").status_code == 200
    assert client.get("/api/customers/stats").status_code == 200
    assert client.get("/api/customers/deleted").status_code == 200
