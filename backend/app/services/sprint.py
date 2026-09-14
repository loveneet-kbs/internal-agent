"""Sprint planning service.

Uses the Groq LLM to decompose a plain-English project goal into a list of
structured sprint tasks, then creates them all in `work_tasks` in one shot.

The LLM is given:
  - the goal
  - the team
  - assignee name hints
  - duration in working days

It returns a JSON array of tasks (title, description, priority, assignee_hint,
day_offset). We validate, resolve assignee IDs, and bulk-insert via the
work_tasks service. No hallucinated IDs reach the database.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from ..errors import ApiError

log = logging.getLogger("app.sprint")

# --------------------------------------------------------------------------- #
# LLM prompt
# --------------------------------------------------------------------------- #
_SYSTEM = """\
You are a senior engineering project manager. Break down the given project goal
into a concrete sprint of individual tasks for the team specified.

Rules:
1. Output ONLY a JSON array — no markdown fences, no explanation.
2. Each element must have exactly these fields:
   - "title": short imperative verb phrase (max 80 chars)
   - "description": 1-2 sentence context / acceptance criteria (max 200 chars)
   - "priority": one of low | medium | high | urgent
   - "assignee_hint": one name from the provided assignees list, or null if unassigned
   - "day_offset": integer >= 0, the number of working days from start_date when this is due
3. Produce between {min_tasks} and {max_tasks} tasks.
4. Vary priority sensibly: not everything is urgent; start with setup tasks,
   then core work, then validation/review.
5. Stagger day_offset: first tasks due sooner (0-3), later tasks further out.
6. If assignees list is empty, set assignee_hint to null for all tasks.
7. Assign tasks evenly across provided assignees.
8. Never invent tasks unrelated to the goal.
"""

_USER = """\
GOAL: {goal}
TEAM: {team}
SPRINT DURATION (working days): {duration_days}
ASSIGNEES: {assignees}
MAX TASKS: {max_tasks}
"""


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _working_day(start: date, offset: int) -> str:
    """Add `offset` working days (Mon-Fri) to `start`."""
    current = start
    added = 0
    while added < offset:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 … Fri=4
            added += 1
    return current.isoformat()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def plan_sprint(
    goal: str,
    team: str | None,
    assignee_names: list[str],
    start_date: str | None,
    duration_days: int,
    max_tasks: int,
) -> dict[str, Any]:
    """Decompose goal → tasks (LLM) → create rows → return sprint payload."""
    # Import lazily so the module stays importable without an API key.
    from ..agent.llm import get_llm
    from . import customers as customer_service
    from . import work_tasks as work_task_service

    # Resolve start date
    try:
        start = date.fromisoformat(start_date) if start_date else date.today()
    except ValueError:
        raise ApiError(400, f'Could not read "{start_date}" as a date. Use YYYY-MM-DD.') from None

    end = _working_day(start, duration_days - 1)

    # Resolve assignee IDs from names
    assignee_map: dict[str, int] = {}  # name → id
    for name in assignee_names:
        person = customer_service.resolve_one(None, name, action="assign sprint tasks to")
        assignee_map[person["name"]] = person["id"]

    resolved_assignees = list(assignee_map.keys())

    # Call the LLM
    llm = get_llm(temperature=0.4)
    min_tasks = max(2, max_tasks // 2)
    response = llm.invoke(
        [
            {
                "role": "system",
                "content": _SYSTEM.format(min_tasks=min_tasks, max_tasks=max_tasks),
            },
            {
                "role": "user",
                "content": _USER.format(
                    goal=goal,
                    team=team or "General",
                    duration_days=duration_days,
                    assignees=", ".join(resolved_assignees) if resolved_assignees else "none",
                    max_tasks=max_tasks,
                ),
            },
        ]
    )

    raw = response.content if isinstance(response.content, str) else ""
    try:
        task_defs: list[dict[str, Any]] = json.loads(_strip_fences(raw))
        if not isinstance(task_defs, list):
            raise ValueError("Not a list")
    except (ValueError, TypeError) as exc:
        log.warning("Sprint LLM returned non-JSON: %s", raw[:300])
        raise ApiError(502, "The AI returned a malformed sprint plan. Try again.") from exc

    if not task_defs:
        raise ApiError(502, "The AI returned an empty sprint plan. Try again.")

    # Create tasks
    created_tasks: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for i, t in enumerate(task_defs[:max_tasks]):
        try:
            title = str(t.get("title") or "").strip()
            if not title:
                skipped.append({"index": i, "reason": "missing title"})
                continue

            hint = t.get("assignee_hint")
            assignee_id: int | None = None
            if hint:
                # Fuzzy match the hint against our resolved map (case-insensitive partial)
                hint_lower = hint.lower()
                for name, aid in assignee_map.items():
                    if hint_lower in name.lower() or name.lower() in hint_lower:
                        assignee_id = aid
                        break

            day_offset = int(t.get("day_offset") or 0)
            due_date = _working_day(start, min(day_offset, duration_days - 1))

            row = work_task_service.create(
                title=title,
                description=str(t.get("description") or "").strip() or None,
                priority=str(t.get("priority") or "medium"),
                assignee_id=assignee_id,
                team=team,
                due_date=due_date,
                created_by="agent:sprint",
            )
            created_tasks.append(row)
        except ApiError as exc:
            skipped.append({"index": i, "title": t.get("title"), "reason": exc.message})
        except Exception as exc:
            skipped.append({"index": i, "title": t.get("title"), "reason": str(exc)})

    if not created_tasks:
        raise ApiError(500, "Sprint planning failed: no tasks could be created.")

    sprint_name = f"{(team or 'Sprint').title()} — {goal[:50]}"

    return {
        "sprint_name": sprint_name,
        "goal": goal,
        "team": team,
        "start_date": start.isoformat(),
        "end_date": end,
        "duration_days": duration_days,
        "assignees": resolved_assignees,
        "tasks": created_tasks,
        "created_count": len(created_tasks),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "summary": {
            "total": len(created_tasks),
            "urgent": sum(1 for t in created_tasks if t["priority"] == "urgent"),
            "high": sum(1 for t in created_tasks if t["priority"] == "high"),
            "medium": sum(1 for t in created_tasks if t["priority"] == "medium"),
            "low": sum(1 for t in created_tasks if t["priority"] == "low"),
            "assigned": sum(1 for t in created_tasks if t.get("assignee_id")),
        },
    }
