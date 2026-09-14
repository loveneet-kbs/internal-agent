"""Service-layer and registry tests."""

from __future__ import annotations

import pytest

from app.agent import tools as registry
from app.errors import ApiError
from app.services import customers as customer_service
from app.services import tasks as task_service


CONTROL_TOOLS = {"request_clarification", "report_unsupported"}


def test_registry_exposes_every_data_tool_and_no_control_tool():
    public = {tool["name"] for tool in registry.list_public_tools()}

    # A subset assertion, so adding a tool does not break this test. The point is
    # that nothing expected has silently gone missing.
    expected = {
        "get_customers",
        "get_customer",
        "search_customers",
        "create_customer",
        "create_customers_bulk",
        "update_customer",
        "delete_customer",
        "restore_customer",
        "add_note",
        "get_notes",
        "team_overview",
        "search_sent_mail",
        "draft_email",
        "get_leave_requests",
        "approve_leave",
        "reject_leave",
        "request_leave",
        "mark_attendance",
        "mark_team_attendance",
        "mark_bulk_attendance",
        "get_attendance",
        "attendance_summary",
        "employee_snapshot",
        "create_task",
        "assign_task",
        "update_task",
        "complete_task",
        "list_tasks",
        "task_summary",
    }
    assert expected <= public, f"missing from the registry: {expected - public}"

    # Control tools are bound to the model but are not part of the public surface.
    assert CONTROL_TOOLS <= set(registry.REGISTRY)
    assert not (CONTROL_TOOLS & public)


def test_registered_tool_names_are_unique():
    names = [spec.name for spec in registry.REGISTRY.values()]
    assert len(names) == len(set(names))


def test_public_tools_carry_ui_metadata():
    for tool in registry.list_public_tools():
        assert tool["method"] in {"GET", "POST", "PUT", "DELETE"}
        assert tool["endpoint"].startswith("/api/")
        assert tool["description"]


def test_no_tool_can_send_mail():
    """Drafting is a tool; sending is not. A prompt must never be able to deliver
    mail on its own - that needs an authenticated human on POST /api/mail/send."""
    import inspect

    from app.services import mail as mail_service

    for spec in registry.REGISTRY.values():
        source = inspect.getsource(spec.tool.func)
        assert "send_email" not in source, f"{spec.name} can send mail"

    assert not hasattr(mail_service.send_email, "__wrapped_as_tool__")


def test_name_search_is_case_insensitive(seeded):
    assert len(customer_service.find_by_name("rahul")) == 1
    assert len(customer_service.find_by_name("RAHUL")) == 1


def test_name_search_escapes_wildcards(seeded):
    """A literal % must not match everything."""
    assert customer_service.find_by_name("%") == []


def test_resolve_one_rejects_ambiguity(seeded):
    with pytest.raises(ApiError) as exc:
        customer_service.resolve_one(None, "Priya", action="delete")
    assert exc.value.status_code == 409


def test_resolve_one_requires_an_identifier():
    with pytest.raises(ApiError) as exc:
        customer_service.resolve_one(None, None, action="update")
    assert exc.value.status_code == 400


def test_update_rejects_unknown_columns(seeded):
    with pytest.raises(ApiError) as exc:
        customer_service.update_customer(seeded[0]["id"], {"is_seed": 1})
    assert "Unsupported field" in exc.value.message


def test_task_error_can_be_cleared():
    """The Node version merged with `??`, so an error could never be unset."""
    task = task_service.create_task("prompt")
    task_service.update_task(task["id"], status="failed", error="boom")
    assert task_service.get_task(task["id"])["error"] == "boom"

    task_service.update_task(task["id"], status="completed", error=None)
    assert task_service.get_task(task["id"])["error"] is None


def test_terminal_status_stamps_completed_at():
    task = task_service.create_task("prompt")
    assert task_service.get_task(task["id"])["completed_at"] is None

    task_service.update_task(task["id"], status="completed")
    assert task_service.get_task(task["id"])["completed_at"] is not None


def test_task_json_columns_round_trip():
    task = task_service.create_task("prompt")
    task_service.update_task(
        task["id"], parameters='{"a": 1}', result='{"message": "ok", "data": []}'
    )
    stored = task_service.get_task(task["id"])
    assert stored["parameters"] == {"a": 1}
    assert stored["result"]["message"] == "ok"


def test_update_task_rejects_unknown_columns():
    task = task_service.create_task("prompt")
    with pytest.raises(ValueError):
        task_service.update_task(task["id"], nonexistent_column="x")


# --------------------------------------------------------------------------- #
# Tool routing - binding all 31 tools cost ~6k tokens on every call
# --------------------------------------------------------------------------- #
def test_routing_narrows_the_toolset():
    from app.agent import routing, tools as registry

    everything = len(registry.BOUND_TOOLS)
    for prompt in [
        "show me all employees",
        "mark everyone present today",
        "approve Karan's leave",
        "what is overdue right now?",
    ]:
        assert len(routing.select(prompt)) < everything, prompt


def test_routing_always_keeps_the_core_tools():
    from app.agent import routing

    for prompt in ["mark everyone present", "what is overdue", "approve leave"]:
        names = {tool.name for tool in routing.select(prompt)}
        assert {"request_clarification", "report_unsupported", "employee_snapshot"} <= names


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("mark everyone present except Ishita", "mark_bulk_attendance"),
        ("approve Priya's leave", "approve_leave"),
        ("reject the leave, not enough balance", "reject_leave"),
        ("what is overdue right now?", "list_tasks"),
        ("create a task for Zoya due Friday", "create_task"),
        ("email Priya about Thursday", "draft_email"),
        ("add a note that Rahul prefers mornings", "add_note"),
        ("delete Sam Dutt", "delete_customer"),
        ("undo that, restore Sam", "restore_customer"),
        ("how many people are on each team?", "team_overview"),
        ("who was absent yesterday?", "get_attendance"),
        ("what is Aisha's workload?", "task_summary"),
    ],
)
def test_routing_includes_the_tool_the_prompt_needs(prompt, expected):
    """A prompt whose tool is not bound cannot be answered at all."""
    from app.agent import routing

    assert expected in {tool.name for tool in routing.select(prompt)}, prompt


def test_tell_me_about_does_not_route_to_mail():
    """'tell' used to fire the mail group; it is a snapshot request."""
    from app.agent import routing

    groups = routing.explain("tell me about Priya Singh")["groups"]
    assert "mail" not in groups


def test_unmatched_prompt_falls_back_to_every_tool():
    """Being stingy would leave the agent unable to act; a retry is cheaper."""
    from app.agent import routing, tools as registry

    assert len(routing.select("xyzzy blorp")) == len(registry.BOUND_TOOLS)


# --------------------------------------------------------------------------- #
# Bulk update - "set everyone's email to firstname_lastname@..." changed one row
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "full_name,expected",
    [
        ("Shiven Goyal", "shiven_goyal@yopmail.com"),
        ("Priya Singh", "priya_singh@yopmail.com"),
        ("Rahul Kumar Sharma", "rahul_sharma@yopmail.com"),   # middle name dropped
        ("Priya O'Neill-Rao", "priya_oneillrao@yopmail.com"),  # punctuation stripped
    ],
)
def test_email_template_renders_per_person(full_name, expected):
    rendered = customer_service.render_template(
        "{first}_{last}@yopmail.com", {"name": full_name}
    )
    assert rendered == expected


def test_update_many_changes_everyone(seeded):
    people = customer_service.search(limit=500)
    outcome = customer_service.update_many(people, {"email": "{first}_{last}@yopmail.com"})

    assert len(outcome["updated"]) == len(people)
    assert all(row["email"].endswith("@yopmail.com") for row in outcome["updated"])
    assert {row["email"] for row in outcome["updated"]} == {
        "rahul_sharma@yopmail.com",
        "priya_singh@yopmail.com",
        "priya_mehta@yopmail.com",
    }


def test_update_many_reports_a_duplicate_instead_of_aborting(seeded):
    """One clash must not discard every other row's update."""
    people = customer_service.search(limit=500)
    # Everyone would collapse to the same address.
    outcome = customer_service.update_many(people, {"email": "shared@yopmail.com"})

    assert len(outcome["updated"]) == 1
    assert len(outcome["skipped"]) == 2
    assert all("already exists" in item["reason"] for item in outcome["skipped"])


def test_update_many_skips_rows_already_correct(seeded):
    people = customer_service.search(limit=500)
    customer_service.update_many(people, {"team": "Design"})

    again = customer_service.update_many(
        customer_service.search(limit=500), {"team": "Design"}
    )
    assert again["updated"] == []
    assert all(item["reason"] == "already set" for item in again["skipped"])


def test_bulk_update_tool_needs_a_scope_and_a_change(seeded):
    from app.agent import tools as registry

    with pytest.raises(ApiError) as no_scope:
        registry._update_customers_bulk(set_email="{first}@x.com")
    assert "everyone, a team, or a list" in no_scope.value.message

    with pytest.raises(ApiError) as no_change:
        registry._update_customers_bulk(everyone=True)
    assert "what to change" in no_change.value.message


def test_bulk_update_tool_end_to_end(seeded):
    from app.agent import tools as registry

    result = registry._update_customers_bulk(
        everyone=True, set_email="{first}_{last}@yopmail.com"
    )
    assert "3 of 3" in result["message"]
    assert all(row["email"].endswith("@yopmail.com") for row in result["data"])


def test_bulk_update_respects_except_names(seeded):
    from app.agent import tools as registry

    registry._update_customers_bulk(
        everyone=True, set_team="Product", except_names=["Rahul Sharma"]
    )
    rahul = customer_service.find_by_name("Rahul Sharma")[0]
    assert rahul["team"] != "Product"


def test_agent_bulk_updates_every_email(stub_model, seeded):
    """The reported bug: this changed one row and then listed customers."""
    from app.agent.service import run_agent

    stub_model(
        "update_customers_bulk",
        {"everyone": True, "set_email": "{first}_{last}@yopmail.com"},
    )
    outcome = run_agent("update all persons email as firstname_lastname@yopmail.com")

    assert outcome["success"] is True
    assert all(
        row["email"].endswith("@yopmail.com")
        for row in customer_service.search(limit=500)
    )
