"""Meetings and calendar service."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any

from ..db import connect
from ..errors import ApiError
from . import customers as customer_service


def _format_row(row: Any, conn: Any = None) -> dict[str, Any]:
    attendees_raw = row["attendees"]
    try:
        attendee_data = json.loads(attendees_raw) if isinstance(attendees_raw, str) else attendees_raw
    except Exception:
        attendee_data = []

    host_name = None
    if row["host_id"] and conn:
        host_row = conn.execute("SELECT name FROM customers WHERE id = ?", (row["host_id"],)).fetchone()
        if host_row:
            host_name = host_row["name"]

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"] or "",
        "team": row["team"] or "",
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "location_or_link": row["location_or_link"] or "Google Meet",
        "host_id": row["host_id"],
        "host_name": host_name,
        "attendees": attendee_data if isinstance(attendee_data, list) else [],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def list_meetings(
    team: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    attendee_name: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List meetings with optional filters."""
    query = ["SELECT * FROM meetings WHERE 1=1"]
    params: list[Any] = []

    if status:
        query.append("AND status = ?")
        params.append(status)
    if team:
        query.append("AND team LIKE ?")
        params.append(f"%{team}%")
    if start_date:
        query.append("AND start_time >= ?")
        params.append(start_date)
    if end_date:
        query.append("AND end_time <= ?")
        params.append(f"{end_date}T23:59:59" if "T" not in end_date else end_date)

    query.append("ORDER BY start_time ASC LIMIT ?")
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(" ".join(query), params).fetchall()
        results = [_format_row(row, conn) for row in rows]

        if attendee_name:
            target = attendee_name.lower().strip()
            filtered = []
            for m in results:
                # Check host name or attendee list
                if m.get("host_name") and target in m["host_name"].lower():
                    filtered.append(m)
                    continue
                has_attendee = False
                for att in m.get("attendees", []):
                    att_str = str(att).lower()
                    if isinstance(att, dict) and target in att.get("name", "").lower():
                        has_attendee = True
                        break
                    elif target in att_str:
                        has_attendee = True
                        break
                if has_attendee:
                    filtered.append(m)
            return filtered

        return results


def get_meeting(meeting_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not row:
            raise ApiError(404, f"Meeting {meeting_id} not found.")
        return _format_row(row, conn)


def create_meeting(
    title: str,
    start_time: str,
    end_time: str | None = None,
    duration_minutes: int = 30,
    host_id: int | None = None,
    host_name: str | None = None,
    attendees: list[str | dict[str, Any]] | None = None,
    team: str | None = None,
    location_or_link: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Schedule a new meeting."""
    if not title or not title.strip():
        raise ApiError(400, "Meeting title cannot be empty.")
    if not start_time:
        raise ApiError(400, "start_time is required.")

    # Parse and normalize start/end time
    start_clean = start_time.replace(" ", "T")
    try:
        dt_start = datetime.fromisoformat(start_clean)
    except Exception as e:
        raise ApiError(400, f"Invalid start_time format '{start_time}'. Use ISO format (YYYY-MM-DDTHH:MM:SS).") from e

    if end_time:
        end_clean = end_time.replace(" ", "T")
        try:
            dt_end = datetime.fromisoformat(end_clean)
        except Exception as e:
            raise ApiError(400, f"Invalid end_time format '{end_time}'.") from e
    else:
        dt_end = dt_start + timedelta(minutes=duration_minutes)

    if dt_end <= dt_start:
        raise ApiError(400, "end_time must be after start_time.")

    # Resolve host
    resolved_host_id = host_id
    if not resolved_host_id and host_name:
        match = customer_service.resolve(host_name)
        if match:
            resolved_host_id = match["id"]
            if not team:
                team = match.get("team")

    # Resolve attendees into structured objects
    resolved_attendees = []
    if attendees:
        for att in attendees:
            if isinstance(att, dict):
                resolved_attendees.append(att)
            elif isinstance(att, (int, str)):
                att_str = str(att).strip()
                if att_str.isdigit():
                    person = customer_service.get(int(att_str))
                    if person:
                        resolved_attendees.append({"id": person["id"], "name": person["name"], "email": person["email"], "team": person.get("team")})
                else:
                    person = customer_service.resolve(att_str)
                    if person:
                        resolved_attendees.append({"id": person["id"], "name": person["name"], "email": person["email"], "team": person.get("team")})
                    else:
                        resolved_attendees.append({"name": att_str})

    with connect() as conn:
        cursor = conn.execute(
            """INSERT INTO meetings
               (title, description, team, start_time, end_time, location_or_link, host_id, attendees, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')""",
            (
                title.strip(),
                (description or "").strip(),
                team or "",
                dt_start.isoformat(),
                dt_end.isoformat(),
                location_or_link or "Google Meet",
                resolved_host_id,
                json.dumps(resolved_attendees),
            ),
        )
        meeting_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        return _format_row(row, conn)


def cancel_meeting(meeting_id: int, reason: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not row:
            raise ApiError(404, f"Meeting {meeting_id} not found.")

        desc = row["description"] or ""
        if reason:
            desc = f"{desc} [Cancelled: {reason}]".strip()

        conn.execute(
            "UPDATE meetings SET status = 'cancelled', description = ? WHERE id = ?",
            (desc, meeting_id),
        )
        updated = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        return _format_row(updated, conn)


def find_free_slots(
    attendees: list[str | int],
    target_date: str,
    duration_minutes: int = 30,
) -> dict[str, Any]:
    """Calculates available meeting slots for a group of people on a specific date."""
    target_date_clean = target_date.split("T")[0].strip()

    # Resolve all attendees
    resolved_people = []
    for att in attendees:
        if isinstance(att, int) or (isinstance(att, str) and att.isdigit()):
            person = customer_service.get(int(att))
            if person:
                resolved_people.append(person)
        elif isinstance(att, str):
            person = customer_service.resolve(att)
            if person:
                resolved_people.append(person)
            else:
                resolved_people.append({"id": None, "name": att})

    # Check leaves and attendance
    conflicts_by_person: dict[str, list[str]] = {}
    with connect() as conn:
        for p in resolved_people:
            pid = p.get("id")
            pname = p.get("name", "Unknown")
            conflicts_by_person[pname] = []

            if pid:
                # Check leave
                leave_row = conn.execute(
                    """SELECT leave_type FROM leave_requests
                       WHERE customer_id = ? AND status = 'approved'
                       AND date(?) BETWEEN date(start_date) AND date(end_date)""",
                    (pid, target_date_clean),
                ).fetchone()
                if leave_row:
                    conflicts_by_person[pname].append(f"On {leave_row['leave_type']} leave")

                # Check attendance
                att_row = conn.execute(
                    "SELECT status FROM attendance WHERE customer_id = ? AND day = ?",
                    (pid, target_date_clean),
                ).fetchone()
                if att_row and att_row["status"] == "absent":
                    conflicts_by_person[pname].append("Marked absent for the day")

        # Existing meetings on this date
        meetings_on_day = conn.execute(
            """SELECT * FROM meetings
               WHERE status = 'scheduled'
               AND (date(start_time) = date(?) OR date(end_time) = date(?))""",
            (target_date_clean, target_date_clean),
        ).fetchall()

    # Generate 30m working hour slots from 09:00 to 18:00
    work_start = datetime.fromisoformat(f"{target_date_clean}T09:00:00")
    work_end = datetime.fromisoformat(f"{target_date_clean}T18:00:00")

    all_slots = []
    current = work_start
    slot_delta = timedelta(minutes=duration_minutes)

    while current + slot_delta <= work_end:
        slot_end = current + slot_delta
        slot_str = current.strftime("%H:%M")
        slot_end_str = slot_end.strftime("%H:%M")

        busy_reasons = []

        # Whole-day conflicts
        for pname, confs in conflicts_by_person.items():
            for c in confs:
                busy_reasons.append(f"{pname}: {c}")

        # Meeting overlaps
        for m in meetings_on_day:
            m_start = datetime.fromisoformat(m["start_time"].replace(" ", "T"))
            m_end = datetime.fromisoformat(m["end_time"].replace(" ", "T"))

            if max(current, m_start) < min(slot_end, m_end):
                m_formatted = _format_row(m)
                m_att_names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in m_formatted["attendees"]]
                if m_formatted.get("host_name"):
                    m_att_names.append(m_formatted["host_name"])

                for p in resolved_people:
                    pname = p.get("name", "")
                    if any(pname.lower() in an.lower() for an in m_att_names if an):
                        busy_reasons.append(f"{pname} has '{m['title']}' ({m_start.strftime('%H:%M')}-{m_end.strftime('%H:%M')})")

        is_available = len(busy_reasons) == 0
        all_slots.append({
            "start": f"{target_date_clean}T{slot_str}:00",
            "end": f"{target_date_clean}T{slot_end_str}:00",
            "time_label": f"{slot_str} - {slot_end_str}",
            "available": is_available,
            "conflicts": list(set(busy_reasons)),
        })
        current += slot_delta

    free_count = sum(1 for s in all_slots if s["available"])

    return {
        "date": target_date_clean,
        "attendees": resolved_people,
        "total_slots": len(all_slots),
        "available_slots_count": free_count,
        "slots": all_slots,
    }
