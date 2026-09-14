"""One employee, everything about them, in a single read.

Answers "tell me about Priya" without the caller chaining six tools - which also
keeps the agent inside its step budget and off the rate limiter.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..db import connect
from ..errors import ApiError
from . import attendance as attendance_service
from . import customers as customer_service
from . import leave as leave_service
from . import notes as note_service
from . import work_tasks as task_service


def _manager(manager_id: int | None) -> dict[str, Any] | None:
    if manager_id is None:
        return None
    found = customer_service.get_customer(manager_id)
    if found is None:
        return None
    return {
        "id": found["id"],
        "name": found["name"],
        "title": found["title"],
        "email": found["email"],
    }


def _reports(customer_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, title FROM customers "
            "WHERE manager_id = ? AND deleted_at IS NULL ORDER BY name COLLATE NOCASE",
            (customer_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _recent_mail(email: str, limit: int = 3) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, subject, sent_at FROM sent_emails "
            "WHERE recipient = ? ORDER BY id DESC LIMIT ?",
            (email, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _tenure(joined_at: str | None) -> str | None:
    if not joined_at:
        return None
    try:
        start = date.fromisoformat(joined_at)
    except ValueError:
        return None
    months = max(0, (date.today() - start).days // 30)
    if months < 12:
        return f"{months} mo"
    years, rest = divmod(months, 12)
    return f"{years}y {rest}mo" if rest else f"{years}y"


def build(customer_id: int) -> dict[str, Any]:
    person = customer_service.get_customer(customer_id)
    if person is None:
        raise ApiError(404, f"No customer found with ID {customer_id}.")

    today = date.today().isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()

    leave_all = leave_service.list_requests(customer_id=customer_id, limit=50)
    pending_leave = [r for r in leave_all if r["status"] == "pending"]
    upcoming_leave = [
        r for r in leave_all if r["status"] == "approved" and r["end_date"] >= today
    ]

    attendance_stats = attendance_service.person_summary(customer_id, since=month_ago)
    today_record = attendance_service.list_records(customer_id=customer_id, day=today)

    open_tasks = task_service.list_tasks(assignee_id=customer_id, open_only=True, limit=10)
    task_stats = task_service.summary(assignee_id=customer_id)

    return {
        "profile": {
            "id": person["id"],
            "name": person["name"],
            "email": person["email"],
            "phone": person["phone"],
            "title": person["title"],
            "team": person["team"],
            "location": person["location"],
            "status": person["status"],
            "joined_at": person["joined_at"],
            "tenure": _tenure(person["joined_at"]),
        },
        "manager": _manager(person.get("manager_id")),
        "direct_reports": _reports(customer_id),
        "attendance": {
            **attendance_stats,
            "today": today_record[0]["status"] if today_record else None,
        },
        "leave": {
            "pending": pending_leave,
            "upcoming_approved": upcoming_leave,
            "pending_count": len(pending_leave),
        },
        "tasks": {**task_stats, "open_items": open_tasks},
        "notes": note_service.list_notes(customer_id, limit=5),
        "recent_emails": _recent_mail(person["email"]),
    }


def headline(snapshot: dict[str, Any]) -> str:
    """A one-line human summary - what the agent says above the detail."""
    profile = snapshot["profile"]
    tasks = snapshot["tasks"]
    attendance = snapshot["attendance"]

    parts = [f"{profile['name']} - {profile['title'] or 'no title'}"]
    if profile["team"]:
        parts.append(f"{profile['team']} team")
    if snapshot["manager"]:
        parts.append(f"reports to {snapshot['manager']['name']}")
    if snapshot["direct_reports"]:
        parts.append(f"{len(snapshot['direct_reports'])} report(s)")

    detail = [f"{tasks['open']} open task(s)"]
    if tasks["overdue"]:
        detail.append(f"{tasks['overdue']} overdue")
    if snapshot["leave"]["pending_count"]:
        detail.append(f"{snapshot['leave']['pending_count']} leave request(s) pending")
    if attendance.get("attendance_rate") is not None:
        detail.append(f"{attendance['attendance_rate']}% attendance over 30 days")

    return ". ".join([", ".join(parts), "; ".join(detail)]) + "."
