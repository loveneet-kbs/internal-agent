"""Daily attendance.

One record per person per day, so marking the same day twice corrects it rather
than stacking duplicates. Approving leave writes `leave` across the covered
working days, which is why the attendance grid and the leave board never disagree.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..db import connect
from ..errors import ApiError

STATUSES = ("present", "absent", "leave", "half_day", "wfh")

# What people actually type, mapped to what the column stores.
_ALIASES = {
    "present": "present", "p": "present", "in": "present", "here": "present",
    "attended": "present", "working": "present",
    "absent": "absent", "a": "absent", "out": "absent", "away": "absent",
    "missing": "absent", "no show": "absent", "noshow": "absent",
    "leave": "leave", "l": "leave", "on leave": "leave", "off": "leave",
    "holiday": "leave", "vacation": "leave", "pto": "leave",
    "half day": "half_day", "half_day": "half_day", "halfday": "half_day", "h": "half_day",
    "wfh": "wfh", "remote": "wfh", "work from home": "wfh", "home": "wfh",
}

LABELS = {
    "present": "Present",
    "absent": "Absent",
    "leave": "Leave",
    "half_day": "Half day",
    "wfh": "Remote",
}


def normalise_status(value: str | None) -> str:
    if not value:
        raise ApiError(400, f"An attendance status is required. Use: {', '.join(STATUSES)}.")
    key = value.strip().lower().replace("-", " ").replace("_", " ")
    resolved = _ALIASES.get(key) or _ALIASES.get(key.replace(" ", ""))
    if resolved is None:
        raise ApiError(
            400, f'Unknown attendance status "{value}". Use: {", ".join(STATUSES)}.'
        )
    return resolved


def parse_day(value: str | None) -> str:
    """Accept an ISO date, or the words people actually use for recent days."""
    if not value:
        return date.today().isoformat()

    key = value.strip().lower()
    today = date.today()

    offsets = {
        "today": 0,
        "yesterday": -1,
        "tomorrow": 1,
        "day before yesterday": -2,
        "last 7 days": -7,
        "past week": -7,
        "last 30 days": -30,
        "past month": -30,
    }
    if key in offsets:
        return (today + timedelta(days=offsets[key])).isoformat()

    # Range words. Used as a `since`, these give the natural starting point.
    if key in ("this week", "current week"):
        return (today - timedelta(days=today.weekday())).isoformat()
    if key == "last week":
        return (today - timedelta(days=today.weekday() + 7)).isoformat()
    if key in ("this month", "current month"):
        return today.replace(day=1).isoformat()

    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise ApiError(
            400, f'Could not read "{value}" as a date. Use YYYY-MM-DD, or "today"/"yesterday".'
        ) from None


SELECT = """
    SELECT a.*, c.name AS person, c.team, c.title
    FROM attendance a
    JOIN customers c ON c.id = a.customer_id
"""


def _rows(cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def mark(
    customer_id: int,
    status: str,
    day: str | None = None,
    note: str | None = None,
    marked_by: str = "agent",
) -> dict[str, Any]:
    resolved_status = normalise_status(status)
    resolved_day = parse_day(day)

    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND deleted_at IS NULL", (customer_id,)
        ).fetchone()
        if not exists:
            raise ApiError(404, f"No customer found with ID {customer_id}.")

        conn.execute(
            """INSERT INTO attendance (customer_id, day, status, note, marked_by)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (customer_id, day) DO UPDATE SET
                   status = excluded.status,
                   note = COALESCE(excluded.note, attendance.note),
                   marked_by = excluded.marked_by,
                   updated_at = datetime('now')""",
            (customer_id, resolved_day, resolved_status, note, marked_by),
        )
        row = conn.execute(
            f"{SELECT} WHERE a.customer_id = ? AND a.day = ?", (customer_id, resolved_day)
        ).fetchone()

    return dict(row)


def mark_many(
    customer_ids: list[int], status: str, day: str | None = None, marked_by: str = "agent"
) -> list[dict[str, Any]]:
    return [mark(cid, status, day, marked_by=marked_by) for cid in customer_ids]


def list_records(
    *,
    customer_id: int | None = None,
    day: str | None = None,
    since: str | None = None,
    until: str | None = None,
    status: str | None = None,
    team: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses = ["c.deleted_at IS NULL"]
    params: list[Any] = []

    if customer_id is not None:
        clauses.append("a.customer_id = ?")
        params.append(customer_id)
    if day:
        clauses.append("a.day = ?")
        params.append(parse_day(day))
    if since:
        clauses.append("a.day >= ?")
        params.append(parse_day(since))
    if until:
        clauses.append("a.day <= ?")
        params.append(parse_day(until))
    if status:
        clauses.append("a.status = ?")
        params.append(normalise_status(status))
    if team:
        clauses.append("c.team LIKE ? COLLATE NOCASE")
        params.append(f"%{team}%")

    params.append(limit)
    with connect() as conn:
        return _rows(
            conn.execute(
                f"{SELECT} WHERE {' AND '.join(clauses)} "
                "ORDER BY a.day DESC, c.name COLLATE NOCASE ASC LIMIT ?",
                params,
            )
        )


def day_summary(day: str | None = None) -> dict[str, Any]:
    """Counts for one day, plus who is unmarked - the gap that matters."""
    target = parse_day(day)
    with connect() as conn:
        counts = conn.execute(
            """SELECT a.status, COUNT(*) AS n
               FROM attendance a JOIN customers c ON c.id = a.customer_id
               WHERE a.day = ? AND c.deleted_at IS NULL
               GROUP BY a.status""",
            (target,),
        ).fetchall()
        headcount = conn.execute(
            "SELECT COUNT(*) AS n FROM customers WHERE deleted_at IS NULL AND status != 'alumni'"
        ).fetchone()["n"]
        unmarked = _rows(
            conn.execute(
                """SELECT c.id, c.name, c.team, c.title
                   FROM customers c
                   WHERE c.deleted_at IS NULL AND c.status != 'alumni'
                     AND NOT EXISTS (
                       SELECT 1 FROM attendance a
                       WHERE a.customer_id = c.id AND a.day = ?)
                   ORDER BY c.name COLLATE NOCASE""",
                (target,),
            )
        )

    tally = {status: 0 for status in STATUSES}
    for row in counts:
        tally[row["status"]] = row["n"]

    return {
        "day": target,
        "headcount": headcount,
        "marked": sum(tally.values()),
        "unmarked": len(unmarked),
        "unmarked_people": unmarked,
        **tally,
    }


def person_summary(customer_id: int, since: str | None = None) -> dict[str, Any]:
    start = parse_day(since) if since else (date.today() - timedelta(days=30)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            """SELECT status, COUNT(*) AS n FROM attendance
               WHERE customer_id = ? AND day >= ? GROUP BY status""",
            (customer_id, start),
        ).fetchall()

    tally = {status: 0 for status in STATUSES}
    for row in rows:
        tally[row["status"]] = row["n"]
    total = sum(tally.values())
    rate = round((tally["present"] + tally["wfh"] + tally["half_day"] * 0.5) / total * 100) if total else None
    return {"since": start, "records": total, "attendance_rate": rate, **tally}


def working_days(start: str, end: str) -> list[str]:
    """Weekdays between two ISO dates, inclusive."""
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return []
    days = []
    current = first
    while current <= last:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days
