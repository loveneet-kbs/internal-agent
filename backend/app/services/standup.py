"""Daily standup digest service.

Aggregates attendance, urgent tasks, today's meetings, pending leaves, and
critical workspace anomalies into a single structured payload that the
`generate_daily_standup_digest` agent tool returns.

Pure database queries — no LLM call, no side effects. Returns quickly even
on a large dataset because every query uses the same indexed columns the rest
of the app targets.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..db import connect


def generate_digest(team: str | None = None) -> dict[str, Any]:
    """Build the complete standup digest for today.

    Args:
        team: Optional team filter. When provided the attendance section and
              task sections are filtered to that team only; meetings and
              anomalies are always company-wide.
    """
    today = date.today().isoformat()
    team_clause = ""
    team_params: list[Any] = []
    if team:
        team_clause = "AND c.team LIKE ? COLLATE NOCASE"
        team_params = [f"%{team}%"]

    with connect() as conn:
        # ------------------------------------------------------------------ #
        # 1. Attendance – today's counts + unmarked count
        # ------------------------------------------------------------------ #
        att_counts = conn.execute(
            f"""SELECT a.status, COUNT(*) AS n
               FROM attendance a
               JOIN customers c ON c.id = a.customer_id
               WHERE a.day = ? AND c.deleted_at IS NULL {team_clause}
               GROUP BY a.status""",
            [today, *team_params],
        ).fetchall()

        total_staff = conn.execute(
            f"""SELECT COUNT(*) AS n FROM customers c
               WHERE c.deleted_at IS NULL AND c.status != 'alumni' {team_clause}""",
            team_params,
        ).fetchone()["n"]

        att_tally: dict[str, int] = {
            "present": 0, "absent": 0, "leave": 0, "half_day": 0, "wfh": 0
        }
        for row in att_counts:
            att_tally[row["status"]] = row["n"]

        marked = sum(att_tally.values())
        unmarked = total_staff - marked

        # Who is unmarked? (first 10 names)
        unmarked_people = conn.execute(
            f"""SELECT c.name, c.team FROM customers c
               WHERE c.deleted_at IS NULL AND c.status != 'alumni'
                 {team_clause}
                 AND NOT EXISTS (
                   SELECT 1 FROM attendance a
                   WHERE a.customer_id = c.id AND a.day = ?)
               ORDER BY c.name COLLATE NOCASE LIMIT 10""",
            [*team_params, today],
        ).fetchall()

        attendance = {
            "date": today,
            "total_staff": total_staff,
            "marked": marked,
            "unmarked": unmarked,
            "unmarked_people": [dict(r) for r in unmarked_people],
            **att_tally,
        }

        # ------------------------------------------------------------------ #
        # 2. Urgent & overdue tasks – due today or already overdue
        # ------------------------------------------------------------------ #
        task_team_clause = ""
        task_team_params: list[Any] = []
        if team:
            task_team_clause = "AND w.team LIKE ? COLLATE NOCASE"
            task_team_params = [f"%{team}%"]

        urgent_tasks = conn.execute(
            f"""SELECT w.id, w.title, w.priority, w.status, w.due_date,
                       c.name AS assignee, w.team
               FROM work_tasks w
               LEFT JOIN customers c ON c.id = w.assignee_id
               WHERE w.status NOT IN ('done', 'cancelled')
                 AND (w.priority IN ('urgent', 'high')
                      OR (w.due_date IS NOT NULL AND w.due_date <= ?))
                 {task_team_clause}
               ORDER BY
                 CASE w.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
                 COALESCE(w.due_date, '9999-12-31') ASC
               LIMIT 15""",
            [today, *task_team_params],
        ).fetchall()

        # Task stats for today
        task_stats = conn.execute(
            f"""SELECT
                 COUNT(*) AS total_open,
                 SUM(CASE WHEN priority = 'urgent' AND status NOT IN ('done','cancelled') THEN 1 ELSE 0 END) AS urgent_open,
                 SUM(CASE WHEN due_date = ? AND status NOT IN ('done','cancelled') THEN 1 ELSE 0 END) AS due_today,
                 SUM(CASE WHEN due_date < ? AND status NOT IN ('done','cancelled') THEN 1 ELSE 0 END) AS overdue
               FROM work_tasks w
               WHERE status NOT IN ('done', 'cancelled')
               {task_team_clause}""",
            [today, today, *task_team_params],
        ).fetchone()

        tasks_section = {
            "urgent_open": task_stats["urgent_open"] or 0,
            "due_today": task_stats["due_today"] or 0,
            "overdue": task_stats["overdue"] or 0,
            "total_open": task_stats["total_open"] or 0,
            "highlight": [dict(r) for r in urgent_tasks],
        }

        # ------------------------------------------------------------------ #
        # 3. Meetings – scheduled for today
        # ------------------------------------------------------------------ #
        today_meetings = conn.execute(
            """SELECT m.id, m.title, m.start_time, m.end_time, m.location_or_link,
                      m.team, c.name AS host_name, m.attendees
               FROM meetings m
               LEFT JOIN customers c ON c.id = m.host_id
               WHERE m.status = 'scheduled'
                 AND date(m.start_time) = ?
               ORDER BY m.start_time ASC
               LIMIT 20""",
            (today,),
        ).fetchall()

        import json as _json
        meetings_list = []
        for m in today_meetings:
            try:
                attendees = _json.loads(m["attendees"]) if m["attendees"] else []
            except Exception:
                attendees = []
            meetings_list.append({
                "id": m["id"],
                "title": m["title"],
                "start_time": m["start_time"],
                "end_time": m["end_time"],
                "location_or_link": m["location_or_link"],
                "team": m["team"],
                "host_name": m["host_name"],
                "attendee_count": len(attendees),
            })

        meetings_section = {
            "count": len(meetings_list),
            "items": meetings_list,
        }

        # ------------------------------------------------------------------ #
        # 4. Pending leave requests
        # ------------------------------------------------------------------ #
        leave_pending = conn.execute(
            """SELECT COUNT(*) AS n FROM leave_requests WHERE status = 'pending'"""
        ).fetchone()["n"]

        leave_today = conn.execute(
            """SELECT l.id, c.name, c.team, l.leave_type, l.start_date, l.end_date
               FROM leave_requests l
               JOIN customers c ON c.id = l.customer_id
               WHERE l.status = 'approved'
                 AND l.start_date <= ? AND l.end_date >= ?
               ORDER BY c.name COLLATE NOCASE
               LIMIT 20""",
            (today, today),
        ).fetchall()

        leave_section = {
            "pending_approval": leave_pending,
            "on_leave_today": len(leave_today),
            "on_leave_people": [dict(r) for r in leave_today],
        }

        # ------------------------------------------------------------------ #
        # 5. Critical anomalies (inline, no extra service call)
        # ------------------------------------------------------------------ #
        unassigned_urgent_count = conn.execute(
            """SELECT COUNT(*) AS n FROM work_tasks
               WHERE assignee_id IS NULL
                 AND status NOT IN ('done','cancelled')
                 AND priority IN ('urgent','high')"""
        ).fetchone()["n"]

        overloaded_people = conn.execute(
            """SELECT c.name, c.team, COUNT(w.id) AS task_count
               FROM customers c
               JOIN work_tasks w ON w.assignee_id = c.id
               WHERE w.status NOT IN ('done','cancelled')
                 AND w.priority IN ('urgent','high')
                 AND c.deleted_at IS NULL
               GROUP BY c.id
               HAVING task_count >= 3
               LIMIT 5""",
        ).fetchall()

        alerts: list[dict[str, Any]] = []
        if unassigned_urgent_count:
            alerts.append({
                "severity": "critical",
                "message": f"{unassigned_urgent_count} unassigned high/urgent task(s) need attention.",
            })
        for p in overloaded_people:
            alerts.append({
                "severity": "warning",
                "message": f"{p['name']} ({p['team']}) has {p['task_count']} high/urgent tasks.",
            })
        if leave_pending >= 3:
            alerts.append({
                "severity": "info",
                "message": f"{leave_pending} leave requests are waiting for approval.",
            })

        anomalies_section = {
            "alert_count": len(alerts),
            "alerts": alerts,
        }

    # ---------------------------------------------------------------------- #
    # Assemble digest
    # ---------------------------------------------------------------------- #
    health = "healthy"
    if any(a["severity"] == "critical" for a in alerts) or tasks_section["overdue"] > 0:
        health = "needs_attention"
    elif any(a["severity"] == "warning" for a in alerts):
        health = "watch"

    return {
        "digest_date": today,
        "team_filter": team,
        "health": health,
        "attendance": attendance,
        "tasks": tasks_section,
        "meetings": meetings_section,
        "leave": leave_section,
        "anomalies": anomalies_section,
    }
