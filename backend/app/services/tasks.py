"""Task history and API activity log."""

from __future__ import annotations

import json
from typing import Any

from ..db import connect

TERMINAL_STATES = ("completed", "failed", "needs_information", "unsupported")


def _parse(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _expand(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["parameters"] = _parse(row.get("parameters"))
    row["result"] = _parse(row.get("result"))
    return row


def create_task(prompt: str) -> dict[str, Any]:
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (prompt, status) VALUES (?, 'running')", (prompt,)
        )
        task_id = cursor.lastrowid
    task = get_task(task_id)
    assert task is not None
    return task


def get_task(task_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _expand(dict(row)) if row else None


def list_tasks(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [_expand(dict(row)) for row in rows]


def count_tasks() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]


def delete_task(task_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0


UPDATABLE = (
    "intent",
    "tool_name",
    "parameters",
    "method",
    "endpoint",
    "status",
    "result",
    "error",
    "duration_ms",
)


def update_task(task_id: int, **fields: Any) -> dict[str, Any] | None:
    """Patch a task. Only keys explicitly passed are written, so an earlier `error`
    can be cleared by passing `error=None` rather than being sticky forever."""
    unknown = set(fields) - set(UPDATABLE)
    if unknown:
        raise ValueError(f"Not updatable: {', '.join(sorted(unknown))}")
    if not fields:
        return get_task(task_id)

    # Column names come from UPDATABLE, never from caller input.
    assignments = [f"{column} = ?" for column in fields]
    values: list[Any] = list(fields.values())

    if fields.get("status") in TERMINAL_STATES:
        assignments.append("completed_at = datetime('now')")

    values.append(task_id)
    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?", values
        )
        if cursor.rowcount == 0:
            return None
    return get_task(task_id)


def log_activity(
    method: str, endpoint: str, status_code: int, duration_ms: int, source: str = "http"
) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO api_activity (method, endpoint, status_code, duration_ms, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (method, endpoint, status_code, duration_ms, source),
        )


def recent_activity(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM api_activity ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def prune_activity(keep: int = 2000) -> None:
    """Keep the activity log bounded; it is a rolling debug view, not an audit trail."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM api_activity WHERE id <= "
            "(SELECT id FROM api_activity ORDER BY id DESC LIMIT 1 OFFSET ?)",
            (keep,),
        )
