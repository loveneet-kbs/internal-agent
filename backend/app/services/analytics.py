"""Analytics and chart generation service."""

from __future__ import annotations

from typing import Any

from ..db import connect
from ..errors import ApiError

PALETTE = [
    "#6366f1",  # indigo / accent
    "#06b6d4",  # cyan
    "#10b981",  # emerald / success
    "#f59e0b",  # amber / warning
    "#ef4444",  # rose / danger
    "#8b5cf6",  # purple
    "#ec4899",  # pink
    "#14b8a6",  # teal
]


def build_chart_data(
    metric: str = "tasks_by_status",
    chart_type: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    """Generates structured chart payloads ready for interactive frontend rendering."""
    with connect() as conn:
        metric_norm = metric.lower().replace("-", "_").strip()

        if metric_norm in ("headcount", "headcount_by_team", "teams", "team_distribution"):
            rows = conn.execute(
                """SELECT COALESCE(team, 'Unassigned') as label, COUNT(*) as value
                   FROM customers
                   WHERE deleted_at IS NULL
                   GROUP BY label
                   ORDER BY value DESC"""
            ).fetchall()
            title = "Team Headcount Distribution"
            subtitle = "Active employees across departments"
            default_type = "donut"

        elif metric_norm in ("tasks_by_status", "task_status", "work_status"):
            query = "SELECT status as label, COUNT(*) as value FROM work_tasks"
            params = []
            if team:
                query += " WHERE team LIKE ?"
                params.append(f"%{team}%")
            query += " GROUP BY status ORDER BY value DESC"
            rows = conn.execute(query, params).fetchall()
            title = f"Task Status Breakdown{f' ({team})' if team else ''}"
            subtitle = "Work items grouped by operational state"
            default_type = "donut"

        elif metric_norm in ("tasks_by_priority", "task_priority", "priority"):
            query = "SELECT priority as label, COUNT(*) as value FROM work_tasks"
            params = []
            if team:
                query += " WHERE team LIKE ?"
                params.append(f"%{team}%")
            query += " GROUP BY priority ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"
            rows = conn.execute(query, params).fetchall()
            title = f"Task Priority Distribution{f' ({team})' if team else ''}"
            subtitle = "Backlog severity levels"
            default_type = "bar"

        elif metric_norm in ("workload_by_team", "tasks_by_team", "team_workload"):
            rows = conn.execute(
                """SELECT COALESCE(team, 'Unassigned') as label, COUNT(*) as value
                   FROM work_tasks
                   WHERE status NOT IN ('done')
                   GROUP BY label
                   ORDER BY value DESC"""
            ).fetchall()
            title = "Open Tasks by Team"
            subtitle = "Active workload across functional groups"
            default_type = "bar"

        elif metric_norm in ("attendance", "attendance_breakdown", "attendance_by_status"):
            rows = conn.execute(
                """SELECT status as label, COUNT(*) as value
                   FROM attendance
                   GROUP BY status
                   ORDER BY value DESC"""
            ).fetchall()
            title = "Overall Attendance Breakdown"
            subtitle = "Historical distribution across work modes"
            default_type = "donut"

        elif metric_norm in ("leave_by_type", "leave_types", "leave_distribution"):
            rows = conn.execute(
                """SELECT leave_type as label, COUNT(*) as value
                   FROM leave_requests
                   GROUP BY leave_type
                   ORDER BY value DESC"""
            ).fetchall()
            title = "Leave Requests by Category"
            subtitle = "Annual, sick, casual, parental distribution"
            default_type = "bar"

        elif metric_norm in ("meetings_by_team", "team_meetings", "meetings"):
            rows = conn.execute(
                """SELECT COALESCE(NULLIF(team, ''), 'General') as label, COUNT(*) as value
                   FROM meetings
                   WHERE status = 'scheduled'
                   GROUP BY label
                   ORDER BY value DESC"""
            ).fetchall()
            title = "Scheduled Meetings by Team"
            subtitle = "Upcoming collaborative events"
            default_type = "bar"

        else:
            # Fallback to team headcount
            rows = conn.execute(
                """SELECT COALESCE(team, 'Unassigned') as label, COUNT(*) as value
                   FROM customers WHERE deleted_at IS NULL GROUP BY label ORDER BY value DESC"""
            ).fetchall()
            title = f"Data Summary: {metric}"
            subtitle = "Aggregated workspace metrics"
            default_type = "bar"

    items = []
    total = sum(r["value"] for r in rows) if rows else 0

    for idx, r in enumerate(rows):
        val = r["value"]
        pct = round((val / total * 100), 1) if total > 0 else 0
        items.append({
            "label": str(r["label"]).capitalize(),
            "value": val,
            "percentage": pct,
            "color": PALETTE[idx % len(PALETTE)],
        })

    resolved_chart_type = (chart_type or default_type).lower()
    if resolved_chart_type not in ("bar", "donut", "pie", "line", "distribution"):
        resolved_chart_type = default_type

    return {
        "metric": metric_norm,
        "title": title,
        "subtitle": subtitle,
        "chart_type": resolved_chart_type,
        "total": total,
        "items": items,
    }
