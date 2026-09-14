"""Anomaly detection and proactive workspace intelligence."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..db import connect


def detect_anomalies() -> dict[str, Any]:
    """Scan database across tasks, attendance, leave, and meetings for bottlenecks, risks, and imbalances."""
    anomalies: list[dict[str, Any]] = []
    today = date.today().isoformat()

    with connect() as conn:
        # 1. Unassigned High/Urgent Priority Tasks
        unassigned_urgent = conn.execute(
            """SELECT id, title, priority, team, due_date
               FROM work_tasks
               WHERE assignee_id IS NULL
                 AND status NOT IN ('done')
                 AND priority IN ('urgent', 'high')"""
        ).fetchall()

        for t in unassigned_urgent:
            anomalies.append({
                "id": f"unassigned-task-{t['id']}",
                "category": "workload",
                "severity": "critical" if t["priority"] == "urgent" else "warning",
                "title": f"Unassigned {t['priority'].upper()} Task",
                "description": f"Task '{t['title']}' for team '{t['team'] or 'General'}' has no assignee.",
                "team": t["team"],
                "entity": {"type": "work_task", "id": t["id"], "title": t["title"]},
                "suggested_action": f"Assign task '{t['title']}' to a team member",
                "prompt_template": f"Assign task {t['id']} to an available engineer in {t['team'] or 'Development'}",
            })

        # 2. Overdue or Blocked Work Tasks
        overdue_tasks = conn.execute(
            """SELECT t.id, t.title, t.priority, t.status, t.due_date, c.name AS assignee_name, t.team
               FROM work_tasks t
               LEFT JOIN customers c ON t.assignee_id = c.id
               WHERE t.status NOT IN ('done')
                 AND (t.status = 'blocked' OR (t.due_date IS NOT NULL AND date(t.due_date) < date(?)))""",
            (today,),
        ).fetchall()

        for t in overdue_tasks:
            is_blocked = t["status"] == "blocked"
            anomalies.append({
                "id": f"overdue-blocked-{t['id']}",
                "category": "workload",
                "severity": "critical" if (is_blocked or t["priority"] == "urgent") else "warning",
                "title": f"Task Blocked / Overdue: {t['title']}",
                "description": (
                    f"'{t['title']}' assigned to {t['assignee_name'] or 'unassigned'} is "
                    + ("BLOCKED" if is_blocked else f"overdue since {t['due_date']}")
                ),
                "team": t["team"],
                "entity": {"type": "work_task", "id": t["id"], "assignee": t["assignee_name"]},
                "suggested_action": f"Review blockers or reassign task {t['id']}",
                "prompt_template": f"Check status of task {t['id']} and draft an update to {t['assignee_name'] or 'the team lead'}",
            })

        # 3. Individual Overload (>3 active high/urgent tasks per person)
        overloaded = conn.execute(
            """SELECT c.id, c.name, c.team, COUNT(t.id) as high_task_count
               FROM customers c
               JOIN work_tasks t ON t.assignee_id = c.id
               WHERE t.status NOT IN ('done') AND t.priority IN ('urgent', 'high')
                 AND c.deleted_at IS NULL
               GROUP BY c.id
               HAVING high_task_count >= 3"""
        ).fetchall()

        for p in overloaded:
            anomalies.append({
                "id": f"person-overload-{p['id']}",
                "category": "capacity",
                "severity": "warning",
                "title": f"Capacity Bottleneck: {p['name']}",
                "description": f"{p['name']} ({p['team']}) currently carries {p['high_task_count']} high/urgent priority tasks.",
                "team": p["team"],
                "entity": {"type": "person", "id": p["id"], "name": p["name"]},
                "suggested_action": f"Redistribute tasks from {p['name']} to other members of {p['team']}",
                "prompt_template": f"List tasks for {p['name']} and reassign one to another {p['team']} teammate",
            })

        # 4. Leave Clashing within Same Team (upcoming overlapping leaves)
        leaves = conn.execute(
            """SELECT l.id, l.customer_id, c.name, c.team, l.start_date, l.end_date, l.status
               FROM leave_requests l
               JOIN customers c ON l.customer_id = c.id
               WHERE l.status IN ('pending', 'approved')
                 AND date(l.end_date) >= date(?)
               ORDER BY c.team, l.start_date""",
            (today,),
        ).fetchall()

        # Group by team and check overlaps
        team_leaves: dict[str, list[Any]] = {}
        for row in leaves:
            t_name = row["team"] or "General"
            team_leaves.setdefault(t_name, []).append(row)

        for t_name, reqs in team_leaves.items():
            if len(reqs) >= 2:
                # Check date overlap
                for i in range(len(reqs)):
                    for j in range(i + 1, len(reqs)):
                        r1, r2 = reqs[i], reqs[j]
                        if r1["customer_id"] != r2["customer_id"]:
                            # Overlap check
                            if max(r1["start_date"], r2["start_date"]) <= min(r1["end_date"], r2["end_date"]):
                                anomalies.append({
                                    "id": f"leave-conflict-{r1['id']}-{r2['id']}",
                                    "category": "attendance",
                                    "severity": "warning",
                                    "title": f"Concurrent Leave Conflict in {t_name}",
                                    "description": f"{r1['name']} and {r2['name']} have overlapping leave between {max(r1['start_date'], r2['start_date'])} and {min(r1['end_date'], r2['end_date'])}.",
                                    "team": t_name,
                                    "entity": {"type": "team", "name": t_name},
                                    "suggested_action": f"Review coverage for {t_name} team before approving pending leave",
                                    "prompt_template": f"Show leave requests for {t_name} team and check available capacity",
                                })
                                break

        # 5. Pending Unresolved Leave Requests
        pending_leaves = conn.execute(
            """SELECT COUNT(*) as count FROM leave_requests WHERE status = 'pending'"""
        ).fetchone()["count"]

        if pending_leaves > 0:
            anomalies.append({
                "id": "pending-leave-backlog",
                "category": "hr",
                "severity": "info" if pending_leaves <= 3 else "warning",
                "title": f"{pending_leaves} Pending Leave Requests",
                "description": f"There are {pending_leaves} leave request(s) awaiting managerial review and approval.",
                "team": None,
                "entity": {"type": "leave_queue", "count": pending_leaves},
                "suggested_action": "Review and decide on pending leave requests",
                "prompt_template": "List all pending leave requests and summarize them",
            })

    # Tally severities
    crit_count = sum(1 for a in anomalies if a["severity"] == "critical")
    warn_count = sum(1 for a in anomalies if a["severity"] == "warning")
    info_count = sum(1 for a in anomalies if a["severity"] == "info")

    return {
        "summary": {
            "critical_count": crit_count,
            "warning_count": warn_count,
            "info_count": info_count,
            "total_anomalies": len(anomalies),
            "status": "critical_issues_found" if crit_count > 0 else ("warnings_present" if warn_count > 0 else "healthy"),
        },
        "anomalies": anomalies,
        "generated_at": today,
    }
