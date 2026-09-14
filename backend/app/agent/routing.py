"""Pick which tools to put in front of the model for a given prompt.

Every bound tool costs tokens on every call, whether or not it is relevant. With
31 tools that was ~5,600 tokens of schema per request - enough to make a simple
lookup slow and to exhaust a 200k/day quota in roughly a dozen runs.

So the prompt is matched against tool groups and only the relevant ones are bound.
The matching is deliberately generous: a group is included if any of its words
appear, a core set is always present, and anything ambiguous falls back to binding
everything. Being wrong here costs a retry; being stingy would break the agent.
"""

from __future__ import annotations

import re

from . import tools as registry

# Always available: the control tools, the "tell me about X" catch-all, and the
# two ways of finding a person - almost every request needs one of those.
CORE = (
    "request_clarification",
    "report_unsupported",
    "employee_snapshot",
    "search_customers",
    "get_customers",
)

GROUPS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # group: (tool names, trigger words)
    "people": (
        (
            "get_customer",
            "create_customer",
            "create_customers_bulk",
            "update_customer",
            "update_customers_bulk",
            "delete_customer",
            "restore_customer",
            "team_overview",
        ),
        (
            "add", "create", "new", "hire", "onboard", "update", "change", "edit",
            "rename", "move", "delete", "remove", "restore", "undo", "team", "teams",
            "headcount", "how many", "employee", "employees", "staff", "people",
            "person", "customer", "directory", "email address", "phone", "title",
            "location", "joined", "alumni", "everyone", "all", "domain",
        ),
    ),
    "snapshot": (
        (),  # employee_snapshot is already in CORE; this group exists to log the intent
        ("tell me about", "summary of", "how is", "overview of", "profile of"),
    ),
    "notes": (
        ("add_note", "get_notes"),
        ("note", "notes", "remember", "know about", "context", "remind"),
    ),
    "leave": (
        ("get_leave_requests", "approve_leave", "reject_leave", "request_leave"),
        (
            "leave", "holiday", "vacation", "pto", "time off", "day off", "days off",
            "approve", "reject", "decline", "sabbatical", "sick", "absence request",
            "parental", "maternity", "paternity", "pending",
        ),
    ),
    "attendance": (
        (
            "mark_attendance",
            "mark_team_attendance",
            "mark_bulk_attendance",
            "get_attendance",
            "attendance_summary",
        ),
        (
            "attendance", "present", "absent", "mark", "here", "wfh", "remote",
            "work from home", "half day", "no show", "turned up", "in today",
            "who is in", "clock",
        ),
    ),
    "tasks": (
        (
            "create_task",
            "assign_task",
            "update_task",
            "complete_task",
            "list_tasks",
            "task_summary",
        ),
        (
            "task", "tasks", "work", "workload", "assign", "assigned", "todo",
            "to do", "backlog", "deadline", "due", "overdue", "priority", "urgent",
            "blocked", "in progress", "complete", "completed", "finish", "done",
            "ticket", "sprint",
        ),
    ),
    "mail": (
        ("draft_email", "search_sent_mail"),
        (
            "email", "mail", "write to", "message", "notify", "inform",
            "send", "draft", "reply", "confirm to", "let them know", "tell them",
            "tell her", "tell him",
        ),
    ),
    "analytics": (
        ("generate_chart",),
        (
            "chart", "graph", "visualize", "visualization", "plot", "pie",
            "donut", "distribution", "breakdown", "analytics", "trends", "metric",
        ),
    ),
    "anomalies": (
        ("detect_workspace_anomalies",),
        (
            "anomaly", "anomalies", "risk", "risks", "bottleneck", "bottlenecks",
            "overloaded", "overload", "clash", "conflict", "scan", "radar",
            "health", "issues", "curious", "investigate",
        ),
    ),
    "meetings": (
        ("schedule_meeting", "find_free_slots", "list_meetings", "cancel_meeting"),
        (
            "meeting", "meetings", "schedule", "calendar", "sync", "slot",
            "slots", "availability", "free time", "available", "call",
            "cancel meeting", "invite", "standup", "1:1", "1-on-1",
        ),
    ),
}


def _matches(prompt: str, words: tuple[str, ...]) -> bool:
    for word in words:
        # Word boundaries so "mark" does not fire on "market", but phrases with
        # spaces are matched plainly.
        if " " in word:
            if word in prompt:
                return True
        elif re.search(rf"\b{re.escape(word)}\b", prompt):
            return True
    return False


def select(prompt: str) -> list:
    """Tools to bind for this prompt. Falls back to all of them when unsure."""
    lowered = prompt.lower()
    chosen: set[str] = set(CORE)

    hit_any = False
    for names, words in GROUPS.values():
        if _matches(lowered, words):
            chosen.update(names)
            hit_any = True

    # No group matched - the prompt is unusual, so give the model everything
    # rather than guess wrong and leave it unable to act.
    if not hit_any:
        return list(registry.BOUND_TOOLS)

    return [
        spec.tool for name, spec in registry.REGISTRY.items() if name in chosen
    ]


def explain(prompt: str) -> dict:
    """Which groups fired, for logging and tests."""
    lowered = prompt.lower()
    fired = [name for name, (_, words) in GROUPS.items() if _matches(lowered, words)]
    return {"groups": fired, "tool_count": len(select(prompt))}
