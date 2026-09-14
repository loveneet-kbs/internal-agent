"""Work assigned to people.

Named `work_tasks` throughout to keep it distinct from the `tasks` table, which is
the agent's own run history. Two different meanings of the same English word, and
conflating them would be a lasting source of confusion.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..db import connect
from ..errors import ApiError

PRIORITIES = ("low", "medium", "high", "urgent")
STATUSES = ("todo", "in_progress", "blocked", "done", "cancelled")
OPEN_STATUSES = ("todo", "in_progress", "blocked")

_PRIORITY_ALIASES = {
    "low": "low", "minor": "low", "p3": "low", "nice to have": "low",
    "medium": "medium", "normal": "medium", "standard": "medium", "p2": "medium",
    "high": "high", "important": "high", "p1": "high",
    "urgent": "urgent", "critical": "urgent", "blocker": "urgent", "p0": "urgent",
    "asap": "urgent",
}

_STATUS_ALIASES = {
    "todo": "todo", "to do": "todo", "open": "todo", "new": "todo", "pending": "todo",
    "backlog": "todo", "not started": "todo",
    "in progress": "in_progress", "in_progress": "in_progress", "started": "in_progress",
    "doing": "in_progress", "active": "in_progress", "wip": "in_progress",
    "blocked": "blocked", "stuck": "blocked", "on hold": "blocked", "waiting": "blocked",
    "done": "done", "complete": "done", "completed": "done", "finished": "done",
    "closed": "done", "shipped": "done",
    "cancelled": "cancelled", "canceled": "cancelled", "dropped": "cancelled",
    "abandoned": "cancelled", "wont do": "cancelled",
}


def _normalise(value: str | None, aliases: dict[str, str], label: str, allowed) -> str | None:
    if not value:
        return None
    key = value.strip().lower().replace("-", " ").replace("_", " ")
    resolved = aliases.get(key) or aliases.get(key.replace(" ", "_"))
    if resolved is None:
        raise ApiError(400, f'Unknown {label} "{value}". Use: {", ".join(allowed)}.')
    return resolved


def normalise_priority(value: str | None) -> str | None:
    return _normalise(value, _PRIORITY_ALIASES, "priority", PRIORITIES)


def normalise_status(value: str | None) -> str | None:
    return _normalise(value, _STATUS_ALIASES, "status", STATUSES)


SELECT = """
    SELECT w.*,
           c.name AS assignee, c.team AS assignee_team, c.title AS assignee_title,
           CASE WHEN w.due_date IS NOT NULL
                 AND w.due_date < date('now')
                 AND w.status NOT IN ('done', 'cancelled')
                THEN 1 ELSE 0 END AS overdue
    FROM work_tasks w
    LEFT JOIN customers c ON c.id = w.assignee_id
"""


def _rows(cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def get_task(task_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(f"{SELECT} WHERE w.id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def create(
    title: str,
    description: str | None = None,
    priority: str = "medium",
    status: str = "todo",
    assignee_id: int | None = None,
    team: str | None = None,
    due_date: str | None = None,
    created_by: str = "agent",
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ApiError(400, "A task needs a title.")

    if assignee_id is not None:
        with connect() as conn:
            exists = conn.execute(
                "SELECT team FROM customers WHERE id = ? AND deleted_at IS NULL",
                (assignee_id,),
            ).fetchone()
        if not exists:
            raise ApiError(404, f"No customer found with ID {assignee_id}.")
        # Default the task's team to the assignee's, so team filters just work.
        team = team or exists["team"]

    if due_date:
        try:
            date.fromisoformat(due_date)
        except ValueError:
            raise ApiError(400, f'Could not read "{due_date}" as a date. Use YYYY-MM-DD.') from None

    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO work_tasks
               (title, description, priority, status, assignee_id, team, due_date, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                (description or "").strip() or None,
                normalise_priority(priority) or "medium",
                normalise_status(status) or "todo",
                assignee_id,
                team,
                due_date,
                created_by,
            ),
        )
        new_id = cursor.lastrowid

    created = get_task(new_id)
    assert created is not None
    return created


EDITABLE = ("title", "description", "priority", "status", "assignee_id", "team", "due_date")


def update(task_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        raise ApiError(400, "No changes were provided.")

    unknown = set(fields) - set(EDITABLE)
    if unknown:
        raise ApiError(400, f"Cannot change: {', '.join(sorted(unknown))}")

    if get_task(task_id) is None:
        return None

    patch = dict(fields)
    if "priority" in patch:
        patch["priority"] = normalise_priority(patch["priority"])
    if "status" in patch:
        patch["status"] = normalise_status(patch["status"])

    # Column names come from EDITABLE, never from caller input.
    assignments = [f"{column} = ?" for column in patch]
    values = list(patch.values())

    # Completion is a fact about time, not just a label - keep the stamp in step.
    if patch.get("status") == "done":
        assignments.append("completed_at = datetime('now')")
    elif "status" in patch:
        assignments.append("completed_at = NULL")

    values.append(task_id)
    with connect() as conn:
        conn.execute(
            f"UPDATE work_tasks SET {', '.join(assignments)}, updated_at = datetime('now') "
            "WHERE id = ?",
            values,
        )
    return get_task(task_id)


def list_tasks(
    *,
    assignee_id: int | None = None,
    team: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    open_only: bool = False,
    overdue_only: bool = False,
    due_before: str | None = None,
    unassigned: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: list[Any] = []

    if assignee_id is not None:
        clauses.append("w.assignee_id = ?")
        params.append(assignee_id)
    if unassigned:
        clauses.append("w.assignee_id IS NULL")
    if team:
        clauses.append("w.team LIKE ? COLLATE NOCASE")
        params.append(f"%{team}%")
    if status:
        clauses.append("w.status = ?")
        params.append(normalise_status(status))
    if priority:
        clauses.append("w.priority = ?")
        params.append(normalise_priority(priority))
    if open_only:
        clauses.append(f"w.status IN ({','.join('?' * len(OPEN_STATUSES))})")
        params.extend(OPEN_STATUSES)
    if overdue_only:
        clauses.append(
            "w.due_date IS NOT NULL AND w.due_date < date('now') "
            "AND w.status NOT IN ('done','cancelled')"
        )
    if due_before:
        clauses.append("w.due_date IS NOT NULL AND w.due_date <= ?")
        params.append(due_before)

    params.append(limit)
    with connect() as conn:
        return _rows(
            conn.execute(
                f"""{SELECT} WHERE {' AND '.join(clauses)}
                    ORDER BY
                      CASE w.status WHEN 'done' THEN 2 WHEN 'cancelled' THEN 3 ELSE 0 END,
                      overdue DESC,
                      CASE w.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                                      WHEN 'medium' THEN 2 ELSE 3 END,
                      COALESCE(w.due_date, '9999-12-31') ASC
                    LIMIT ?""",
                params,
            )
        )


def summary(assignee_id: int | None = None, team: str | None = None) -> dict[str, Any]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if assignee_id is not None:
        clauses.append("w.assignee_id = ?")
        params.append(assignee_id)
    if team:
        clauses.append("w.team LIKE ? COLLATE NOCASE")
        params.append(f"%{team}%")

    where = " AND ".join(clauses)
    with connect() as conn:
        counts = conn.execute(
            f"""SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN w.status = 'todo'        THEN 1 ELSE 0 END) AS todo,
                  SUM(CASE WHEN w.status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
                  SUM(CASE WHEN w.status = 'blocked'     THEN 1 ELSE 0 END) AS blocked,
                  SUM(CASE WHEN w.status = 'done'        THEN 1 ELSE 0 END) AS done,
                  SUM(CASE WHEN w.status = 'cancelled'   THEN 1 ELSE 0 END) AS cancelled,
                  SUM(CASE WHEN w.due_date IS NOT NULL AND w.due_date < date('now')
                            AND w.status NOT IN ('done','cancelled')
                           THEN 1 ELSE 0 END) AS overdue,
                  SUM(CASE WHEN w.priority = 'urgent' AND w.status NOT IN ('done','cancelled')
                           THEN 1 ELSE 0 END) AS urgent_open,
                  SUM(CASE WHEN w.priority = 'high' AND w.status NOT IN ('done','cancelled')
                           THEN 1 ELSE 0 END) AS high_open
                FROM work_tasks w WHERE {where}""",
            params,
        ).fetchone()

    data = {key: (counts[key] or 0) for key in counts.keys()}
    data["open"] = data["todo"] + data["in_progress"] + data["blocked"]
    data["completion_rate"] = (
        round(data["done"] / data["total"] * 100) if data["total"] else None
    )
    return data


def rebalance_team(
    team: str,
    max_moves: int = 3,
    overload_threshold: int = 3,
) -> dict[str, Any]:
    """Redistribute tasks from overloaded team members to those with fewer open tasks.

    A member is considered overloaded when their open (non-done, non-cancelled,
    non-blocked) task count is >= overload_threshold. The lightest-loaded member
    on the same team receives each redistributed task.

    Returns a report dict with:
      - moved: list of {task_id, title, from_name, to_name}
      - overloaded_before: snapshot of the overloaded people
      - skipped_reason: set when nothing could be moved
    """
    with connect() as conn:
        # All active team members
        members = conn.execute(
            """SELECT c.id, c.name,
                  COUNT(w.id) AS open_count
               FROM customers c
               LEFT JOIN work_tasks w
                 ON w.assignee_id = c.id
                 AND w.status NOT IN ('done', 'cancelled', 'blocked')
               WHERE c.deleted_at IS NULL
                 AND c.team LIKE ? COLLATE NOCASE
                 AND c.status = 'active'
               GROUP BY c.id
               ORDER BY open_count DESC""",
            (f"%{team}%",),
        ).fetchall()

    if not members:
        raise ApiError(404, f'No active members found on the "{team}" team.')

    member_loads = {row["id"]: {"name": row["name"], "open": row["open_count"]} for row in members}

    overloaded = [row for row in members if row["open_count"] >= overload_threshold]
    available = sorted(members, key=lambda r: r["open_count"])

    if not overloaded:
        return {
            "moved": [],
            "overloaded_before": [],
            "skipped_reason": (
                f"Nobody on the {team} team has {overload_threshold}+ open tasks. "
                "Workload is already balanced."
            ),
            "summary": f"No rebalancing needed for the {team} team.",
        }

    # Collect tasks from overloaded members (non-blocked, non-urgent, moveable)
    candidates: list[dict[str, Any]] = []
    for person in overloaded:
        tasks = list_tasks(
            assignee_id=person["id"],
            open_only=True,
            limit=10,
        )
        # Prefer moving medium/low priority, leave urgent/high with the person
        moveable = [
            t for t in tasks
            if t["status"] not in ("blocked", "done", "cancelled")
            and t["priority"] in ("medium", "low")
        ]
        candidates.extend(moveable)

    if not candidates:
        # Fall back: allow moving high priority if nothing else exists
        for person in overloaded:
            tasks = list_tasks(assignee_id=person["id"], open_only=True, limit=10)
            moveable = [t for t in tasks if t["status"] not in ("blocked", "done", "cancelled")]
            candidates.extend(moveable)

    if not candidates:
        return {
            "moved": [],
            "overloaded_before": [{"name": r["name"], "open": r["open_count"]} for r in overloaded],
            "skipped_reason": "All tasks from overloaded members are blocked or urgent — not safe to move.",
            "summary": f"Could not rebalance the {team} team: all tasks are blocked or critical.",
        }

    moved: list[dict[str, Any]] = []
    # Track live load changes in memory so we always give tasks to the lightest
    live_load: dict[int, int] = {row["id"]: row["open_count"] for row in members}

    for task in candidates[:max_moves]:
        from_id = task["assignee_id"]
        from_name = member_loads.get(from_id, {}).get("name", "?")

        # Pick the member with the fewest tasks (excluding the current assignee)
        receiver = min(
            [r for r in members if r["id"] != from_id],
            key=lambda r: live_load.get(r["id"], 0),
        )

        updated = update(task["id"], {"assignee_id": receiver["id"]})
        if updated:
            live_load[receiver["id"]] = live_load.get(receiver["id"], 0) + 1
            live_load[from_id] = max(0, live_load.get(from_id, 1) - 1)
            moved.append({
                "task_id": task["id"],
                "title": task["title"],
                "priority": task["priority"],
                "from_name": from_name,
                "to_name": receiver["name"],
            })

        overloaded_snapshot = [{"name": r["name"], "open": r["open_count"]} for r in overloaded]

        if moved:
            moved_text = "; ".join(
                '"{}" → {}'.format(m["title"], m["to_name"])
                for m in moved
            )
            summary = f"Moved {len(moved)} task(s) on the {team} team: {moved_text}"
        else:
            summary = f"No tasks were moved on the {team} team."

    return {
        "moved": moved,
        "overloaded_before": overloaded_snapshot,
        "team": team,
        "skipped_reason": None,
        "summary": summary,
    }
