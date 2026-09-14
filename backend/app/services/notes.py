"""Free-text notes against a person."""

from __future__ import annotations

from typing import Any

from ..db import connect
from ..errors import ApiError


def add_note(customer_id: int, body: str, author: str = "agent") -> dict[str, Any]:
    body = (body or "").strip()
    if not body:
        raise ApiError(400, "A note cannot be empty.")
    if len(body) > 2000:
        raise ApiError(400, "A note must be 2000 characters or fewer.")

    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND deleted_at IS NULL", (customer_id,)
        ).fetchone()
        if not exists:
            raise ApiError(404, f"No customer found with ID {customer_id}.")

        cursor = conn.execute(
            "INSERT INTO notes (customer_id, body, author) VALUES (?, ?, ?)",
            (customer_id, body, author),
        )
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_notes(customer_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE customer_id = ? ORDER BY id DESC LIMIT ?",
            (customer_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_note(note_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount > 0
