"""Leave requests: reading them, and approving or rejecting a pending one.

Deciding a request is not just a status flip. If the leave covers today, the
person's own `status` moves to `on_leave` so the directory, the team view and
`search_customers(status="on_leave")` all agree with the decision - one action,
one consistent picture.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..db import connect
from ..errors import ApiError

TYPES = ("annual", "sick", "casual", "unpaid", "parental")
STATUSES = ("pending", "approved", "rejected", "cancelled")

_TYPE_ALIASES = {
    "annual": "annual", "holiday": "annual", "vacation": "annual", "pto": "annual",
    "sick": "sick", "medical": "sick", "illness": "sick",
    "casual": "casual", "personal": "casual",
    "unpaid": "unpaid", "loa": "unpaid",
    "parental": "parental", "maternity": "parental", "paternity": "parental",
}


def normalise_type(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower().replace("-", " ").replace("_", " ").split()[0]
    resolved = _TYPE_ALIASES.get(key)
    if resolved is None:
        raise ApiError(400, f'Unknown leave type "{value}". Use: {", ".join(TYPES)}.')
    return resolved


SELECT = """
    SELECT l.*, c.name AS person, c.team, c.title, c.email
    FROM leave_requests l
    JOIN customers c ON c.id = l.customer_id
"""


def _rows(cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def list_requests(
    *,
    customer_id: int | None = None,
    status: str | None = None,
    leave_type: str | None = None,
    team: str | None = None,
    starting_after: str | None = None,
    starting_before: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["c.deleted_at IS NULL"]
    params: list[Any] = []

    if customer_id is not None:
        clauses.append("l.customer_id = ?")
        params.append(customer_id)
    if status:
        if status not in STATUSES:
            raise ApiError(400, f'Unknown status "{status}". Use: {", ".join(STATUSES)}.')
        clauses.append("l.status = ?")
        params.append(status)
    if leave_type:
        clauses.append("l.leave_type = ?")
        params.append(normalise_type(leave_type))
    if team:
        clauses.append("c.team LIKE ? COLLATE NOCASE")
        params.append(f"%{team}%")
    if starting_after:
        clauses.append("l.start_date >= ?")
        params.append(starting_after)
    if starting_before:
        clauses.append("l.start_date <= ?")
        params.append(starting_before)

    params.append(limit)
    with connect() as conn:
        return _rows(
            conn.execute(
                f"{SELECT} WHERE {' AND '.join(clauses)} "
                "ORDER BY CASE l.status WHEN 'pending' THEN 0 ELSE 1 END, l.start_date ASC "
                "LIMIT ?",
                params,
            )
        )


def get_request(request_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(f"{SELECT} WHERE l.id = ?", (request_id,)).fetchone()
    return dict(row) if row else None


def pending_for(customer_id: int) -> list[dict[str, Any]]:
    return list_requests(customer_id=customer_id, status="pending")


def _covers_today(request: dict[str, Any]) -> bool:
    today = date.today().isoformat()
    return str(request["start_date"]) <= today <= str(request["end_date"])


def _resolve_pending(request_id: int | None, customer_id: int | None) -> dict[str, Any]:
    """Find the one pending request being decided, or explain why we cannot."""
    if request_id is not None:
        found = get_request(request_id)
        if found is None:
            raise ApiError(404, f"No leave request with ID {request_id}.")
        if found["status"] != "pending":
            raise ApiError(
                409,
                f"That request is already {found['status']} - "
                f"{found['person']}'s {found['start_date']} to {found['end_date']}.",
            )
        return found

    if customer_id is None:
        raise ApiError(400, "A leave request ID or a person is required.")

    pending = pending_for(customer_id)
    if not pending:
        raise ApiError(404, "That person has no pending leave requests.")
    if len(pending) > 1:
        options = "; ".join(
            f"#{r['id']} {r['start_date']} to {r['end_date']} ({r['days']}d, {r['leave_type']})"
            for r in pending
        )
        raise ApiError(
            409, f"There are {len(pending)} pending requests - which one? {options}"
        )
    return pending[0]


def decide(
    *,
    request_id: int | None = None,
    customer_id: int | None = None,
    approve: bool,
    note: str | None = None,
    decided_by: str = "agent",
) -> dict[str, Any]:
    """Approve or reject one pending request, keeping the person's status in step."""
    target = _resolve_pending(request_id, customer_id)
    new_status = "approved" if approve else "rejected"

    with connect() as conn:
        conn.execute(
            "UPDATE leave_requests SET status = ?, decided_at = datetime('now'), "
            "decided_by = ?, decision_note = ? WHERE id = ?",
            (new_status, decided_by, note, target["id"]),
        )

        # Keep the person's own status truthful: an approved leave covering today
        # means they are on leave right now, and everything that filters on status
        # should say so.
        status_changed = False
        if approve and _covers_today(target):
            conn.execute(
                "UPDATE customers SET status = 'on_leave', updated_at = datetime('now') "
                "WHERE id = ? AND status = 'active'",
                (target["customer_id"],),
            )
            status_changed = True

    # Write the approved days straight into attendance, so the grid and the leave
    # board can never disagree about why someone was out.
    days_marked = 0
    if approve:
        from . import attendance as attendance_service

        for day in attendance_service.working_days(target["start_date"], target["end_date"]):
            attendance_service.mark(
                target["customer_id"],
                "leave",
                day,
                note=f"Approved {target['leave_type']} leave",
                marked_by=decided_by,
            )
            days_marked += 1

    updated = get_request(target["id"])
    assert updated is not None
    return {
        "request": updated,
        "status_changed": status_changed,
        "attendance_days_marked": days_marked,
    }


def create_request(
    customer_id: int,
    start_date: str,
    end_date: str,
    leave_type: str = "annual",
    reason: str | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    if end_date < start_date:
        raise ApiError(400, "The end date cannot be before the start date.")

    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM customers WHERE id = ? AND deleted_at IS NULL", (customer_id,)
        ).fetchone()
        if not exists:
            raise ApiError(404, f"No customer found with ID {customer_id}.")

        cursor = conn.execute(
            "INSERT INTO leave_requests (customer_id, leave_type, start_date, end_date, "
            "days, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (
                customer_id,
                normalise_type(leave_type) or "annual",
                start_date,
                end_date,
                days or _working_days(start_date, end_date),
                reason,
            ),
        )
        new_id = cursor.lastrowid

    created = get_request(new_id)
    assert created is not None
    return created


def _working_days(start: str, end: str) -> int:
    """Inclusive day count, skipping weekends. Good enough without a holiday calendar."""
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        return 1
    if last < first:
        return 1
    total = 0
    current = first
    while current <= last:
        if current.weekday() < 5:
            total += 1
        current = date.fromordinal(current.toordinal() + 1)
    return max(1, total)


def summary() -> dict[str, Any]:
    with connect() as conn:
        counts = conn.execute(
            """SELECT
                 SUM(CASE WHEN l.status = 'pending'  THEN 1 ELSE 0 END) AS pending,
                 SUM(CASE WHEN l.status = 'approved' THEN 1 ELSE 0 END) AS approved,
                 SUM(CASE WHEN l.status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
                 COUNT(*) AS total
               FROM leave_requests l
               JOIN customers c ON c.id = l.customer_id
               WHERE c.deleted_at IS NULL"""
        ).fetchone()
    return {key: (counts[key] or 0) for key in ("pending", "approved", "rejected", "total")}
