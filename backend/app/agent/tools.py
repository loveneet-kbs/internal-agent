"""The agent's tool registry.

Each tool is a real LangChain tool whose implementation calls the same service layer
the HTTP routes use - so "the agent ran a tool" and "the backend did the work" are
the same event, and every run leaves a row in `api_activity`.

The model can only ever emit a call to a name in `REGISTRY`; anything else is
rejected by the graph before execution.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..errors import ApiError
from ..schemas import EMAIL_RE
from ..services import analytics as analytics_service
from ..services import anomalies as anomalies_service
from ..services import attendance as attendance_service
from ..services import customers as customer_service
from ..services import leave as leave_service
from ..services import mail as mail_service
from ..services import meetings as meetings_service
from ..services import notes as note_service
from ..services import snapshot as snapshot_service
from ..services import sprint as sprint_service
from ..services import standup as standup_service
from ..services import tasks as task_service
from ..services import work_tasks as work_task_service


# --------------------------------------------------------------------------- #
# Argument schemas
# --------------------------------------------------------------------------- #
class GetCustomersArgs(BaseModel):
    name: str = Field(
        default="",
        description="Partial name. Omit for everyone.",
    )


class GetCustomerArgs(BaseModel):
    customer_id: int = Field(description="Customer ID.", gt=0)


TEAM_HINT = "Design|AI|Development|QA|Product."


class SearchCustomersArgs(BaseModel):
    name: str | None = Field(default=None, description="Part of a name.")
    team: str | None = Field(default=None, description=f"Filter by team. {TEAM_HINT}")
    title: str | None = Field(
        default=None, description="Part of a job title."
    )
    email_contains: str | None = Field(
        default=None, description="Part of an email."
    )
    phone_contains: str | None = Field(default=None, description="Part of a phone.")
    location: str | None = Field(default=None, description="City or office.")
    status: str | None = Field(default=None, description="One of: active, on_leave, alumni.")
    joined_after: str | None = Field(default=None, description="ISO date.")
    joined_before: str | None = Field(default=None, description="ISO date.")
    sort: str = Field(default="id", description="id|name|team|joined_at|created_at.")
    descending: bool = Field(default=True, description="Descending.")
    limit: int = Field(default=50, ge=1, le=200, description="Max rows.")


class CreateCustomerArgs(BaseModel):
    name: str = Field(description="Full name.", min_length=1)
    email: str = Field(description="Email.", min_length=3)
    phone: str = Field(default="", description="Phone.")
    team: str | None = Field(default=None, description=f"Their team. {TEAM_HINT}")
    title: str | None = Field(default=None, description="Job title.")
    location: str | None = Field(default=None, description="City.")
    joined_at: str | None = Field(default=None, description="Join date, ISO.")


class NewPerson(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    phone: str = Field(default="")
    team: str | None = None
    title: str | None = None
    location: str | None = None
    joined_at: str | None = None


class CreateManyArgs(BaseModel):
    people: list[NewPerson] = Field(
        min_length=1, max_length=50, description="People to add."
    )


class RestoreCustomerArgs(BaseModel):
    customer_id: int | None = Field(
        default=None, description="ID of the deleted customer, when known.", gt=0
    )
    match_name: str | None = Field(
        default=None,
        description=(
            "Name of the deleted person. This searches the recycle bin directly, so use "
            "it straight away - do not look them up with another tool first, they will "
            "not appear in normal results."
        ),
    )


class AddNoteArgs(BaseModel):
    customer_id: int | None = Field(default=None, description="Person ID.")
    match_name: str | None = Field(
        default=None, description="Their name."
    )
    body: str = Field(description="Note text.", min_length=1, max_length=2000)


class GetNotesArgs(BaseModel):
    customer_id: int | None = Field(default=None, description="Person ID.")
    match_name: str | None = Field(default=None, description="Their name.")


class TeamOverviewArgs(BaseModel):
    pass


class SearchSentMailArgs(BaseModel):
    recipient: str | None = Field(
        default=None, description="Part of recipient name/email."
    )
    contains: str | None = Field(
        default=None, description="Text in subject or body."
    )
    limit: int = Field(default=25, ge=1, le=100)


class UpdateCustomerArgs(BaseModel):
    customer_id: int | None = Field(
        default=None, description="Customer ID (preferred)."
    )
    match_name: str | None = Field(
        default=None,
        description=(
            "Existing name used to FIND the customer, when no ID was given. "
            "This is never the new value."
        ),
    )
    new_name: str | None = Field(
        default=None, description="The new name, only when the customer is being renamed."
    )
    email: str | None = Field(default=None, description="New email.")
    phone: str | None = Field(default=None, description="New phone.")
    team: str | None = Field(default=None, description=f"Move them to a team. {TEAM_HINT}")
    title: str | None = Field(default=None, description="New job title.")
    location: str | None = Field(default=None, description="New city.")
    status: str | None = Field(
        default=None, description="active|on_leave|alumni."
    )


class DeleteCustomerArgs(BaseModel):
    customer_id: int | None = Field(
        default=None, description="Customer ID (preferred)."
    )
    match_name: str | None = Field(
        default=None, description="Name to find them by."
    )


class DraftEmailArgs(BaseModel):
    recipient_name: str | None = Field(
        default=None,
        description=(
            "Name of the person to email. This tool looks their address up in the "
            "records automatically, so pass the name alone - never ask the user for "
            "their email address."
        ),
    )
    recipient_email: str | None = Field(
        default=None,
        description=(
            "Only when the user typed an actual email address. Leave empty if you "
            "were given a name."
        ),
    )
    purpose: str = Field(
        description="What the email is about, in a short phrase. e.g. 'project delay update'.",
        min_length=1,
    )
    details: str = Field(
        default="",
        description=(
            "Every concrete fact from the user's request that belongs in the email: "
            "dates, amounts, the action being requested. Copy them faithfully."
        ),
    )
    tone: str = Field(
        default="professional",
        description="One of: professional, friendly, formal, concise.",
    )


class GetLeaveArgs(BaseModel):
    match_name: str | None = Field(
        default=None, description="Whose leave. Omit for everyone."
    )
    status: str | None = Field(
        default="pending",
        description="pending|approved|rejected|cancelled.",
    )
    team: str | None = Field(default=None, description=f"Filter by team. {TEAM_HINT}")
    leave_type: str | None = Field(
        default=None, description="annual|sick|casual|unpaid|parental."
    )
    limit: int = Field(default=50, ge=1, le=200)


class DecideLeaveArgs(BaseModel):
    request_id: int | None = Field(
        default=None, description="Leave request ID.", gt=0
    )
    match_name: str | None = Field(
        default=None,
        description=(
            "The person whose pending leave this is. If they have exactly one pending "
            "request it is used; if several, you are told which ones to choose from."
        ),
    )
    note: str | None = Field(
        default=None, description="Optional decision note."
    )


class RejectLeaveArgs(DecideLeaveArgs):
    note: str = Field(
        description="Why it is being rejected. Required - the person deserves a reason.",
        min_length=1,
    )


class RequestLeaveArgs(BaseModel):
    match_name: str | None = Field(default=None, description="Who it is for.")
    customer_id: int | None = Field(default=None, description="Their ID.", gt=0)
    start_date: str = Field(description="First day, ISO.")
    end_date: str = Field(description="Last day, ISO.")
    leave_type: str = Field(
        default="annual", description="annual|sick|casual|unpaid|parental."
    )
    reason: str | None = Field(default=None, description="Reason.")


ATTENDANCE_HINT = "present|absent|leave|half_day|wfh (everyday words map too)."
DAY_HINT = 'ISO date or "today"/"yesterday"/"this week". Defaults to today.'


class MarkAttendanceArgs(BaseModel):
    match_name: str | None = Field(default=None, description="Whose attendance.")
    customer_id: int | None = Field(default=None, description="Their ID.", gt=0)
    status: str = Field(description=f"How to mark them. {ATTENDANCE_HINT}", min_length=1)
    day: str | None = Field(default=None, description=DAY_HINT)
    note: str | None = Field(default=None, description="Optional note.")


class MarkTeamAttendanceArgs(BaseModel):
    team: str | None = Field(default=None, description=f"Mark a whole team. {TEAM_HINT}")
    names: list[str] | None = Field(
        default=None, max_length=100, description="Specific people."
    )
    status: str = Field(description=f"How to mark them. {ATTENDANCE_HINT}", min_length=1)
    day: str | None = Field(default=None, description=DAY_HINT)


class MarkBulkAttendanceArgs(BaseModel):
    everyone: bool = Field(
        default=False,
        description=(
            "Set true for 'mark everyone', 'mark all staff', 'the whole company'. "
            "Covers every active person."
        ),
    )
    team: str | None = Field(default=None, description=f"Or just one team. {TEAM_HINT}")
    names: list[str] | None = Field(
        default=None, max_length=100, description="Specific people."
    )
    except_names: list[str] | None = Field(
        default=None,
        max_length=50,
        description=(
            "People to leave out, for 'everyone except X'. They are skipped entirely - "
            "mark them separately afterwards if they need a different status."
        ),
    )
    status: str = Field(description=f"How to mark them. {ATTENDANCE_HINT}", min_length=1)
    day: str | None = Field(default=None, description=DAY_HINT)


class GetAttendanceArgs(BaseModel):
    match_name: str | None = Field(
        default=None, description="One person. Omit for everyone."
    )
    day: str | None = Field(default=None, description=DAY_HINT)
    since: str | None = Field(default=None, description="Range start, ISO.")
    until: str | None = Field(default=None, description="Range end, ISO.")
    status: str | None = Field(default=None, description=f"Filter. {ATTENDANCE_HINT}")
    team: str | None = Field(default=None, description=f"Filter by team. {TEAM_HINT}")
    limit: int = Field(default=100, ge=1, le=500)


class AttendanceSummaryArgs(BaseModel):
    day: str | None = Field(default=None, description=DAY_HINT)
    match_name: str | None = Field(
        default=None,
        description="For one person's attendance rate over the last 30 days instead.",
    )


PRIORITY_HINT = "low|medium|high|urgent."
TASK_STATUS_HINT = "todo|in_progress|blocked|done|cancelled."


class SnapshotArgs(BaseModel):
    match_name: str | None = Field(default=None, description="Who.")
    customer_id: int | None = Field(default=None, description="Their ID.", gt=0)


class CreateTaskArgs(BaseModel):
    title: str = Field(description="Task title.", min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assignee_name: str | None = Field(
        default=None, description="Assignee. Empty = unassigned."
    )
    team: str | None = Field(default=None, description=f"Owning team. {TEAM_HINT}")
    priority: str = Field(default="medium", description=PRIORITY_HINT)
    due_date: str | None = Field(default=None, description="Deadline, ISO.")


class AssignTaskArgs(BaseModel):
    task_id: int = Field(description="Task ID.", gt=0)
    assignee_name: str | None = Field(default=None, description="Assignee.")
    team: str | None = Field(
        default=None, description=f"Or hand it to a team without a named owner. {TEAM_HINT}"
    )


class UpdateTaskArgs(BaseModel):
    task_id: int = Field(description="Task ID.", gt=0)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, description=TASK_STATUS_HINT)
    priority: str | None = Field(default=None, description=PRIORITY_HINT)
    due_date: str | None = Field(default=None, description="New deadline, ISO.")
    assignee_name: str | None = Field(default=None, description="Reassign to.")


class CompleteTaskArgs(BaseModel):
    task_id: int = Field(description="Task ID.", gt=0)
    note: str | None = Field(default=None, max_length=500, description="Closing note.")


class ListTasksArgs(BaseModel):
    assignee_name: str | None = Field(default=None, description="This person only.")
    team: str | None = Field(default=None, description=f"Only this team's. {TEAM_HINT}")
    status: str | None = Field(default=None, description=TASK_STATUS_HINT)
    priority: str | None = Field(default=None, description=PRIORITY_HINT)
    open_only: bool = Field(default=False, description="Exclude done/cancelled.")
    overdue_only: bool = Field(default=False, description="Past deadline only.")
    unassigned: bool = Field(default=False, description="Nobody assigned.")
    limit: int = Field(default=50, ge=1, le=200)


class TaskSummaryArgs(BaseModel):
    assignee_name: str | None = Field(default=None, description="One person.")
    team: str | None = Field(default=None, description=f"Or a team's. {TEAM_HINT}")


class BulkUpdateArgs(BaseModel):
    everyone: bool = Field(
        default=False, description="Set true for 'everyone / all staff / all employees'."
    )
    match_team: str | None = Field(default=None, description=f"Or one team. {TEAM_HINT}")
    names: list[str] | None = Field(
        default=None, max_length=100, description="Or these people by name."
    )
    except_names: list[str] | None = Field(
        default=None, max_length=50, description="People to leave untouched."
    )
    set_email: str | None = Field(
        default=None,
        description=(
            "New email. Supports per-person placeholders: {first} {last} {full} "
            "{initials} {team}. For 'firstname_lastname@yopmail.com' pass exactly "
            "'{first}_{last}@yopmail.com' - never expand it yourself."
        ),
    )
    set_team: str | None = Field(default=None, description=f"Move them to a team. {TEAM_HINT}")
    set_title: str | None = Field(default=None, description="New job title. Placeholders allowed.")
    set_location: str | None = Field(default=None, description="New city. Placeholders allowed.")
    set_status: str | None = Field(default=None, description="active|on_leave|alumni.")


class ClarifyArgs(BaseModel):
    question: str = Field(
        description="The specific missing detail to ask the user for, phrased as a question."
    )


class UnsupportedArgs(BaseModel):
    reason: str = Field(description="Why no available tool can satisfy this request.")


class DetectAnomaliesArgs(BaseModel):
    pass


CHART_METRIC_HINT = (
    "tasks_by_status|tasks_by_priority|headcount_by_team|workload_by_team|"
    "attendance_breakdown|leave_by_type|meetings_by_team"
)
CHART_TYPE_HINT = "bar|donut|pie|line|distribution."


class GenerateChartArgs(BaseModel):
    metric: str = Field(
        default="tasks_by_status",
        description=f"Metric dataset to visualize: {CHART_METRIC_HINT}.",
    )
    chart_type: str | None = Field(
        default=None,
        description=f"Chart style. {CHART_TYPE_HINT}",
    )
    team: str | None = Field(
        default=None,
        description=f"Optional team filter. {TEAM_HINT}",
    )


class ScheduleMeetingArgs(BaseModel):
    title: str = Field(description="Topic or title of the meeting.", min_length=1, max_length=200)
    start_time: str = Field(description="ISO start date & time (e.g. 2026-09-01T15:00:00).")
    end_time: str | None = Field(default=None, description="Optional ISO end date & time.")
    duration_minutes: int = Field(default=30, description="Duration in minutes if end_time not given.", ge=5, le=480)
    host_name: str | None = Field(default=None, description="Host or organizer name.")
    attendees: list[str] = Field(default_factory=list, description="Attendee names, emails or IDs.")
    team: str | None = Field(default=None, description=f"Team tag. {TEAM_HINT}")
    location_or_link: str | None = Field(default="Google Meet", description="Meeting room or video URL.")
    description: str | None = Field(default=None, description="Agenda notes or description.")


class FindFreeSlotsArgs(BaseModel):
    attendees: list[str] = Field(description="List of attendee names to check availability for.", min_length=1)
    target_date: str = Field(description="Target date in ISO format YYYY-MM-DD.")
    duration_minutes: int = Field(default=30, description="Slot duration in minutes.", ge=15, le=240)


class ListMeetingsArgs(BaseModel):
    team: str | None = Field(default=None, description=f"Filter by team. {TEAM_HINT}")
    start_date: str | None = Field(default=None, description="Start date ISO.")
    end_date: str | None = Field(default=None, description="End date ISO.")
    attendee_name: str | None = Field(default=None, description="Filter for meetings involving this person.")
    status: str | None = Field(default=None, description="scheduled|cancelled|completed.")
    limit: int = Field(default=50, ge=1, le=200)


class CancelMeetingArgs(BaseModel):
    meeting_id: int = Field(description="ID of the meeting to cancel.", gt=0)
    reason: str | None = Field(default=None, description="Reason for cancellation.")


class PlanSprintArgs(BaseModel):
    goal: str = Field(
        description=(
            "Plain-English description of the project or feature to build. "
            "The AI will decompose this into individual sprint tasks."
        ),
        min_length=5,
        max_length=500,
    )
    team: str | None = Field(default=None, description=f"Team tag for all tasks. {TEAM_HINT}")
    assignee_names: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Names of people to distribute tasks among. Leave empty for unassigned.",
    )
    start_date: str | None = Field(
        default=None,
        description="Sprint start date ISO (YYYY-MM-DD). Defaults to today.",
    )
    duration_days: int = Field(
        default=10,
        ge=3,
        le=90,
        description="Sprint length in working days.",
    )
    max_tasks: int = Field(
        default=6,
        ge=2,
        le=20,
        description="Maximum number of tasks to create.",
    )


class RebalanceWorkloadArgs(BaseModel):
    team: str = Field(
        description=f"Team whose workload to rebalance. {TEAM_HINT}",
        min_length=1,
    )
    max_moves: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of tasks to redistribute.",
    )
    overload_threshold: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Open task count that qualifies someone as overloaded.",
    )


class DailyStandupArgs(BaseModel):
    team: str | None = Field(
        default=None,
        description=f"Restrict the digest to one team's view. {TEAM_HINT} Omit for company-wide.",
    )


# --------------------------------------------------------------------------- #
# Implementations
# --------------------------------------------------------------------------- #
def _get_customers(name: str = "") -> dict[str, Any]:
    data = customer_service.find_by_name(name) if name else customer_service.list_customers()
    scope = f' matching "{name}"' if name else ""
    return {"message": f"Found {len(data)} customer(s){scope}.", "data": data}


def _get_customer(customer_id: int) -> dict[str, Any]:
    found = customer_service.get_customer(customer_id)
    if found is None:
        raise ApiError(404, f"No customer found with ID {customer_id}.")
    return {"message": "Customer found.", "data": found}


def _search_customers(**filters) -> dict[str, Any]:
    limit = filters.pop("limit", 50)
    sort = filters.pop("sort", "id")
    descending = filters.pop("descending", True)
    active = {k: v for k, v in filters.items() if v}

    data = customer_service.search(sort=sort, descending=descending, limit=limit, **active)
    described = ", ".join(f"{k}={v}" for k, v in active.items()) or "no filters"
    return {"message": f"Found {len(data)} customer(s) ({described}).", "data": data}


def _create_customer(
    name: str,
    email: str,
    phone: str = "",
    team: str | None = None,
    title: str | None = None,
    location: str | None = None,
    joined_at: str | None = None,
) -> dict[str, Any]:
    created = customer_service.create_customer(
        name=name,
        email=email,
        phone=phone or None,
        team=team,
        title=title,
        location=location,
        joined_at=joined_at,
    )
    return {"message": "Customer created successfully.", "data": created}


def _create_customers_bulk(people: list[Any]) -> dict[str, Any]:
    records = [p.model_dump(exclude_none=True) if hasattr(p, "model_dump") else dict(p) for p in people]
    outcome = customer_service.create_many(records)

    created, skipped = outcome["created"], outcome["skipped"]
    message = f"Added {len(created)} customer(s)."
    if skipped:
        detail = "; ".join(
            f"{item['name'] or 'row ' + str(item['index'])}: {item['reason']}" for item in skipped
        )
        message += f" Skipped {len(skipped)} - {detail}"

    return {"message": message, "data": created, "skipped": skipped}


def _restore_customer(
    customer_id: int | None = None, match_name: str | None = None
) -> dict[str, Any]:
    target = customer_service.resolve_deleted(customer_id, match_name)
    restored = customer_service.restore_customer(target["id"])
    if restored is None:
        raise ApiError(404, f"Could not restore {target['name']}.")
    return {"message": f"Restored {restored['name']}.", "data": restored}


def _add_note(body: str, customer_id: int | None = None, match_name: str | None = None) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="add a note to")
    note = note_service.add_note(target["id"], body)
    return {"message": f"Note added to {target['name']}.", "data": note}


def _get_notes(customer_id: int | None = None, match_name: str | None = None) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="read notes for")
    notes = note_service.list_notes(target["id"])
    return {"message": f"{len(notes)} note(s) for {target['name']}.", "data": notes}


def _team_overview() -> dict[str, Any]:
    data = customer_service.stats()
    lines = ", ".join(f"{t['team']} {t['headcount']}" for t in data["teams"])
    return {"message": f"{data['total']} people. {lines}.", "data": data}


def _search_sent_mail(
    recipient: str | None = None, contains: str | None = None, limit: int = 25
) -> dict[str, Any]:
    data = mail_service.search_sent(recipient=recipient, contains=contains, limit=limit)
    return {"message": f"Found {len(data)} sent email(s).", "data": data}


def _update_customer(
    customer_id: int | None = None,
    match_name: str | None = None,
    new_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    team: str | None = None,
    title: str | None = None,
    location: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="update")

    fields: dict[str, Any] = {}
    if new_name:
        fields["name"] = new_name
    for key, value in (
        ("email", email),
        ("phone", phone),
        ("team", team),
        ("title", title),
        ("location", location),
        ("status", status),
    ):
        if value:
            fields[key] = value

    if not fields:
        raise ApiError(
            400,
            "No new values were provided. Say what should change, for example "
            '"set their phone to 9876543210".',
        )

    updated = customer_service.update_customer(target["id"], fields)
    return {"message": "Customer updated successfully.", "data": updated}


def _delete_customer(
    customer_id: int | None = None, match_name: str | None = None
) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="delete")
    customer_service.delete_customer(target["id"])
    return {"message": "Customer deleted successfully.", "data": target}


def _draft_email(
    purpose: str,
    recipient_name: str | None = None,
    recipient_email: str | None = None,
    details: str = "",
    tone: str = "professional",
) -> dict[str, Any]:
    """Compose an email and hand it back for review. Sends nothing.

    Delivery is a separate, authenticated step (POST /api/mail/send), so a prompt
    can never cause mail to leave the building on its own.
    """
    # Imported here rather than at module scope: drafting imports the LLM module,
    # and keeping it lazy means the tool registry stays importable without a key.
    from ..services import drafting

    to_address = (recipient_email or "").strip()
    to_name = (recipient_name or "").strip()

    if not to_address:
        if not to_name:
            raise ApiError(
                400,
                "Who should this email go to? Give me a name or an email address.",
            )
        match = customer_service.resolve_one(None, to_name, action="email")
        to_address = match["email"]
        to_name = match["name"]

    if EMAIL_RE.match(to_address) is None:
        raise ApiError(400, f'"{to_address}" is not a valid email address.')

    draft = drafting.generate_draft(
        recipient=to_name or to_address,
        purpose=purpose,
        details=details,
        tone=tone,
    )

    return {
        "message": f"Drafted an email to {to_name or to_address}. Review it, then send.",
        "data": {
            # The frontend switches on `kind` to render the approval card.
            "kind": "email_draft",
            "requires_approval": True,
            "to": to_address,
            "to_name": to_name or None,
            "subject": draft["subject"],
            "body": draft["body"],
            "tone": tone,
        },
    }


def _get_leave_requests(
    match_name: str | None = None,
    status: str | None = "pending",
    team: str | None = None,
    leave_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    customer_id = None
    who = ""
    if match_name:
        target = customer_service.resolve_one(None, match_name, action="look up leave for")
        customer_id = target["id"]
        who = f" for {target['name']}"

    data = leave_service.list_requests(
        customer_id=customer_id,
        status=status or None,
        leave_type=leave_type,
        team=team,
        limit=limit,
    )
    label = f"{status} " if status else ""
    scope = f" on the {team} team" if team else ""
    return {"message": f"Found {len(data)} {label}leave request(s){who}{scope}.", "data": data}


def _decide_leave(
    approve: bool,
    request_id: int | None,
    match_name: str | None,
    note: str | None,
) -> dict[str, Any]:
    customer_id = None
    if request_id is None:
        if not match_name:
            raise ApiError(400, "Whose leave should I decide? Give me a name or a request ID.")
        target = customer_service.resolve_one(None, match_name, action="decide leave for")
        customer_id = target["id"]

    outcome = leave_service.decide(
        request_id=request_id, customer_id=customer_id, approve=approve, note=note
    )
    request = outcome["request"]
    verb = "Approved" if approve else "Rejected"
    message = (
        f"{verb} {request['person']}'s {request['leave_type']} leave, "
        f"{request['start_date']} to {request['end_date']} ({request['days']} day(s))."
    )
    if outcome.get("attendance_days_marked"):
        message += f" Marked {outcome['attendance_days_marked']} day(s) as leave in attendance."
    if outcome["status_changed"]:
        message += f" {request['person']} is now shown as on leave."

    return {"message": message, "data": request}


def _approve_leave(
    request_id: int | None = None, match_name: str | None = None, note: str | None = None
) -> dict[str, Any]:
    return _decide_leave(True, request_id, match_name, note)


def _reject_leave(
    note: str, request_id: int | None = None, match_name: str | None = None
) -> dict[str, Any]:
    return _decide_leave(False, request_id, match_name, note)


def _request_leave(
    start_date: str,
    end_date: str,
    match_name: str | None = None,
    customer_id: int | None = None,
    leave_type: str = "annual",
    reason: str | None = None,
) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="request leave for")
    created = leave_service.create_request(
        customer_id=target["id"],
        start_date=start_date,
        end_date=end_date,
        leave_type=leave_type,
        reason=reason,
    )
    return {
        "message": (
            f"Logged a {created['leave_type']} leave request for {target['name']}, "
            f"{created['start_date']} to {created['end_date']} ({created['days']} day(s)). "
            "It is pending approval."
        ),
        "data": created,
    }


def _mark_attendance(
    status: str,
    match_name: str | None = None,
    customer_id: int | None = None,
    day: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="mark attendance for")
    record = attendance_service.mark(target["id"], status, day, note=note)
    label = attendance_service.LABELS[record["status"]]
    return {
        "message": f"Marked {target['name']} as {label} on {record['day']}.",
        "data": record,
    }


def _mark_bulk_attendance(
    status: str,
    everyone: bool = False,
    team: str | None = None,
    names: list[str] | None = None,
    except_names: list[str] | None = None,
    day: str | None = None,
) -> dict[str, Any]:
    if not (everyone or team or names):
        raise ApiError(
            400, "Tell me who to mark: everyone, a team, or a list of names."
        )

    on_leave_skipped = 0
    if everyone:
        # People already on leave keep their leave record - marking them present
        # would be wrong, so they are left out and the message says so.
        people = customer_service.search(status="active", limit=500)
        on_leave_skipped = len(customer_service.search(status="on_leave", limit=500))
        scope = "all active staff"
    elif team:
        people = customer_service.search(team=team, status="active", limit=500)
        if not people:
            raise ApiError(404, f'No active people found on the "{team}" team.')
        scope = f"the {team} team"
    else:
        people = [
            customer_service.resolve_one(None, name, action="mark attendance for")
            for name in names or []
        ]
        scope = "the named people"

    excluded = []
    if except_names:
        skip_ids = set()
        for name in except_names:
            match = customer_service.resolve_one(None, name, action="exclude")
            skip_ids.add(match["id"])
            excluded.append(match["name"])
        people = [person for person in people if person["id"] not in skip_ids]

    if not people:
        raise ApiError(400, "That leaves nobody to mark.")

    records = attendance_service.mark_many([p["id"] for p in people], status, day)
    label = attendance_service.LABELS[records[0]["status"]]
    message = f"Marked {scope} ({len(records)}) as {label} on {records[0]['day']}."
    if excluded:
        message += f" Skipped {', '.join(excluded)}."
    if on_leave_skipped:
        message += f" {on_leave_skipped} already on leave were left as they are."
    return {"message": message, "data": records}


def _mark_team_attendance(
    status: str,
    team: str | None = None,
    names: list[str] | None = None,
    day: str | None = None,
) -> dict[str, Any]:
    """Team- or list-scoped marking. Shares the bulk implementation so the two
    tools can never drift apart."""
    if not team and not names:
        raise ApiError(400, "Give me a team or a list of names to mark.")
    return _mark_bulk_attendance(status=status, team=team, names=names, day=day)


def _get_attendance(
    match_name: str | None = None,
    day: str | None = None,
    since: str | None = None,
    until: str | None = None,
    status: str | None = None,
    team: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    customer_id = None
    who = ""
    if match_name:
        target = customer_service.resolve_one(None, match_name, action="look up attendance for")
        customer_id = target["id"]
        who = f" for {target['name']}"

    data = attendance_service.list_records(
        customer_id=customer_id,
        day=day,
        since=since,
        until=until,
        status=status,
        team=team,
        limit=limit,
    )
    when = f" on {attendance_service.parse_day(day)}" if day else ""
    what = f" marked {attendance_service.LABELS[attendance_service.normalise_status(status)]}" if status else ""
    return {"message": f"Found {len(data)} attendance record(s){what}{who}{when}.", "data": data}


def _attendance_summary(
    day: str | None = None, match_name: str | None = None
) -> dict[str, Any]:
    if match_name:
        target = customer_service.resolve_one(None, match_name, action="summarise attendance for")
        data = attendance_service.person_summary(target["id"])
        rate = f"{data['attendance_rate']}%" if data["attendance_rate"] is not None else "n/a"
        return {
            "message": (
                f"{target['name']} since {data['since']}: {data['present']} present, "
                f"{data['absent']} absent, {data['leave']} on leave. Attendance {rate}."
            ),
            "data": {**data, "person": target["name"]},
        }

    data = attendance_service.day_summary(day)
    return {
        "message": (
            f"{data['day']}: {data['present']} present, {data['absent']} absent, "
            f"{data['leave']} on leave, {data['wfh']} remote. "
            f"{data['unmarked']} of {data['headcount']} not marked yet."
        ),
        "data": data,
    }


def _employee_snapshot(
    match_name: str | None = None, customer_id: int | None = None
) -> dict[str, Any]:
    target = customer_service.resolve_one(customer_id, match_name, action="summarise")
    data = snapshot_service.build(target["id"])
    return {"message": snapshot_service.headline(data), "data": data}


def _resolve_assignee(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    return customer_service.resolve_one(None, name, action="assign work to")


def _create_task(
    title: str,
    description: str | None = None,
    assignee_name: str | None = None,
    team: str | None = None,
    priority: str = "medium",
    due_date: str | None = None,
) -> dict[str, Any]:
    assignee = _resolve_assignee(assignee_name)
    created = work_task_service.create(
        title=title,
        description=description,
        priority=priority,
        assignee_id=assignee["id"] if assignee else None,
        team=team,
        due_date=due_date,
    )
    who = f" and assigned it to {assignee['name']}" if assignee else " (unassigned)"
    when = f", due {created['due_date']}" if created["due_date"] else ""
    return {
        "message": f'Created task #{created["id"]} "{created["title"]}"{who}{when}.',
        "data": created,
    }


def _assign_task(
    task_id: int, assignee_name: str | None = None, team: str | None = None
) -> dict[str, Any]:
    if not assignee_name and not team:
        raise ApiError(400, "Give me a person or a team to assign this to.")

    fields: dict[str, Any] = {}
    label = ""
    if assignee_name:
        assignee = _resolve_assignee(assignee_name)
        fields["assignee_id"] = assignee["id"]
        label = assignee["name"]
    if team:
        fields["team"] = team
        label = label or f"the {team} team"

    updated = work_task_service.update(task_id, fields)
    if updated is None:
        raise ApiError(404, f"No task with ID {task_id}.")
    return {"message": f'Assigned "{updated["title"]}" to {label}.', "data": updated}


def _update_task(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    assignee_name: str | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in (
        ("title", title),
        ("description", description),
        ("status", status),
        ("priority", priority),
        ("due_date", due_date),
    ):
        if value:
            fields[key] = value
    if assignee_name:
        fields["assignee_id"] = _resolve_assignee(assignee_name)["id"]

    if not fields:
        raise ApiError(400, "Tell me what to change on that task.")

    updated = work_task_service.update(task_id, fields)
    if updated is None:
        raise ApiError(404, f"No task with ID {task_id}.")

    changed = ", ".join(key.replace("assignee_id", "assignee") for key in fields)
    return {"message": f'Updated {changed} on "{updated["title"]}".', "data": updated}


def _complete_task(task_id: int, note: str | None = None) -> dict[str, Any]:
    existing = work_task_service.get_task(task_id)
    if existing is None:
        raise ApiError(404, f"No task with ID {task_id}.")
    if existing["status"] == "done":
        raise ApiError(
            409,
            f'"{existing["title"]}" was already completed on {existing["completed_at"]}.',
        )

    fields: dict[str, Any] = {"status": "done"}
    if note:
        joined = f"{existing['description']}\n\n{note}" if existing["description"] else note
        fields["description"] = joined

    updated = work_task_service.update(task_id, fields)
    who = f" for {updated['assignee']}" if updated["assignee"] else ""
    return {"message": f'Completed "{updated["title"]}"{who}.', "data": updated}


def _list_tasks(
    assignee_name: str | None = None,
    team: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    open_only: bool = False,
    overdue_only: bool = False,
    unassigned: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    assignee = _resolve_assignee(assignee_name) if assignee_name else None
    data = work_task_service.list_tasks(
        assignee_id=assignee["id"] if assignee else None,
        team=team,
        status=status,
        priority=priority,
        open_only=open_only,
        overdue_only=overdue_only,
        unassigned=unassigned,
        limit=limit,
    )

    scope = []
    if assignee:
        scope.append(f"for {assignee['name']}")
    if team:
        scope.append(f"on the {team} team")
    if overdue_only:
        scope.append("overdue")
    elif open_only:
        scope.append("still open")
    if status:
        scope.append(f"marked {status}")
    where = " " + " ".join(scope) if scope else ""
    return {"message": f"Found {len(data)} task(s){where}.", "data": data}


def _task_summary(assignee_name: str | None = None, team: str | None = None) -> dict[str, Any]:
    assignee = _resolve_assignee(assignee_name) if assignee_name else None
    data = work_task_service.summary(
        assignee_id=assignee["id"] if assignee else None, team=team
    )
    whose = assignee["name"] if assignee else (f"the {team} team" if team else "everyone")
    overdue = f", {data['overdue']} overdue" if data["overdue"] else ""
    rate = (
        f" ({data['completion_rate']}% complete)"
        if data["completion_rate"] is not None
        else ""
    )
    return {
        "message": (
            f"{whose}: {data['total']} task(s) - {data['open']} open, "
            f"{data['done']} done{overdue}{rate}."
        ),
        "data": {**data, "scope": whose},
    }


def _update_customers_bulk(
    everyone: bool = False,
    match_team: str | None = None,
    names: list[str] | None = None,
    except_names: list[str] | None = None,
    set_email: str | None = None,
    set_team: str | None = None,
    set_title: str | None = None,
    set_location: str | None = None,
    set_status: str | None = None,
) -> dict[str, Any]:
    if not (everyone or match_team or names):
        raise ApiError(400, "Tell me who to update: everyone, a team, or a list of names.")

    fields: dict[str, Any] = {}
    for key, value in (
        ("email", set_email),
        ("team", set_team),
        ("title", set_title),
        ("location", set_location),
        ("status", set_status),
    ):
        if value:
            fields[key] = value
    if not fields:
        raise ApiError(400, "Tell me what to change.")

    if everyone:
        people = customer_service.search(limit=500)
        scope = "everyone"
    elif match_team:
        people = customer_service.search(team=match_team, limit=500)
        if not people:
            raise ApiError(404, f'Nobody found on the "{match_team}" team.')
        scope = f"the {match_team} team"
    else:
        people = [
            customer_service.resolve_one(None, name, action="update") for name in names or []
        ]
        scope = "the named people"

    excluded = []
    if except_names:
        skip = set()
        for name in except_names:
            match = customer_service.resolve_one(None, name, action="exclude")
            skip.add(match["id"])
            excluded.append(match["name"])
        people = [person for person in people if person["id"] not in skip]

    outcome = customer_service.update_many(people, fields)
    updated, skipped = outcome["updated"], outcome["skipped"]

    changed = ", ".join(fields)
    message = f"Updated {changed} for {len(updated)} of {len(people)} people ({scope})."
    if excluded:
        message += f" Skipped {', '.join(excluded)}."
    problems = [item for item in skipped if item["reason"] != "already set"]
    if problems:
        detail = "; ".join(f"{item['name']}: {item['reason']}" for item in problems[:5])
        message += f" {len(problems)} failed - {detail}"

    return {"message": message, "data": updated, "skipped": skipped}


def _request_clarification(question: str) -> dict[str, Any]:
    return {"message": question, "data": None}


def _report_unsupported(reason: str) -> dict[str, Any]:
    return {"message": reason, "data": None}


def _detect_workspace_anomalies() -> dict[str, Any]:
    report = anomalies_service.detect_anomalies()
    total = report["summary"]["total_anomalies"]
    crit = report["summary"]["critical_count"]
    warn = report["summary"]["warning_count"]
    msg = f"Found {total} workspace anomaly/risk item(s): {crit} critical, {warn} warnings."
    return {"message": msg, "data": report}


def _generate_chart(
    metric: str = "tasks_by_status",
    chart_type: str | None = None,
    team: str | None = None,
) -> dict[str, Any]:
    data = analytics_service.build_chart_data(metric=metric, chart_type=chart_type, team=team)
    msg = f"Generated {data['chart_type']} chart for '{data['title']}' ({data['total']} total items)."
    return {"message": msg, "data": data}


def _schedule_meeting(
    title: str,
    start_time: str,
    end_time: str | None = None,
    duration_minutes: int = 30,
    host_name: str | None = None,
    attendees: list[str] | None = None,
    team: str | None = None,
    location_or_link: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    meeting = meetings_service.create_meeting(
        title=title,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
        host_name=host_name,
        attendees=attendees,
        team=team,
        location_or_link=location_or_link,
        description=description,
    )
    att_count = len(meeting.get("attendees", []))
    msg = f"Scheduled '{meeting['title']}' for {meeting['start_time']} ({att_count} attendee(s))."
    return {"message": msg, "data": meeting}


def _find_free_slots(
    attendees: list[str],
    target_date: str,
    duration_minutes: int = 30,
) -> dict[str, Any]:
    slots_data = meetings_service.find_free_slots(
        attendees=attendees,
        target_date=target_date,
        duration_minutes=duration_minutes,
    )
    free = slots_data["available_slots_count"]
    total = slots_data["total_slots"]
    msg = f"Found {free} of {total} available {duration_minutes}m slot(s) on {slots_data['date']}."
    return {"message": msg, "data": slots_data}


def _list_meetings(
    team: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    attendee_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    meetings = meetings_service.list_meetings(
        team=team,
        start_date=start_date,
        end_date=end_date,
        attendee_name=attendee_name,
        status=status,
        limit=limit,
    )
    msg = f"Found {len(meetings)} meeting(s)."
    return {"message": msg, "data": meetings}


def _cancel_meeting(meeting_id: int, reason: str | None = None) -> dict[str, Any]:
    meeting = meetings_service.cancel_meeting(meeting_id, reason=reason)
    msg = f"Meeting #{meeting_id} ('{meeting['title']}') was cancelled."
    return {"message": msg, "data": meeting}


def _plan_sprint(
    goal: str,
    team: str | None = None,
    assignee_names: list[str] | None = None,
    start_date: str | None = None,
    duration_days: int = 10,
    max_tasks: int = 6,
) -> dict[str, Any]:
    data = sprint_service.plan_sprint(
        goal=goal,
        team=team,
        assignee_names=assignee_names or [],
        start_date=start_date,
        duration_days=duration_days,
        max_tasks=max_tasks,
    )
    msg = (
        f"Sprint '{data['sprint_name']}' planned: {data['created_count']} task(s) created "
        f"({data['start_date']} → {data['end_date']})."
    )
    if data["skipped_count"]:
        msg += f" {data['skipped_count']} skipped."
    return {"message": msg, "data": data}


def _rebalance_team_workload(
    team: str,
    max_moves: int = 3,
    overload_threshold: int = 3,
) -> dict[str, Any]:
    data = work_task_service.rebalance_team(
        team=team,
        max_moves=max_moves,
        overload_threshold=overload_threshold,
    )
    return {"message": data["summary"], "data": data}


def _generate_daily_standup_digest(team: str | None = None) -> dict[str, Any]:
    data = standup_service.generate_digest(team=team)
    att = data["attendance"]
    tasks = data["tasks"]
    meets = data["meetings"]
    scope = f" ({team} team)" if team else ""
    msg = (
        f"Standup digest{scope} for {data['digest_date']}: "
        f"{att['present']} present, {att['absent']} absent, {att['wfh']} remote. "
        f"{tasks['urgent_open']} urgent tasks open, {tasks['overdue']} overdue. "
        f"{meets['count']} meeting(s) today."
    )
    return {"message": msg, "data": data}


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
class ToolSpec(BaseModel):
    name: str
    description: str
    method: str
    endpoint: str
    tool: Any
    mutating: bool = False
    control: bool = False  # control tools answer the user; they touch no data
    success_label: str = "Records read"

    model_config = {"arbitrary_types_allowed": True}


def _spec(
    name: str,
    description: str,
    method: str,
    endpoint: str,
    func,
    args_schema: type[BaseModel],
    *,
    mutating: bool = False,
    control: bool = False,
    success_label: str | None = None,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        method=method,
        endpoint=endpoint,
        mutating=mutating,
        control=control,
        success_label=success_label or ("Database updated" if mutating else "Records read"),
        tool=StructuredTool.from_function(
            func=func, name=name, description=description, args_schema=args_schema
        ),
    )


_SPECS = [
    _spec(
        "get_customers",
        "List everyone, or filter by partial name.",
        "GET",
        "/api/customers",
        _get_customers,
        GetCustomersArgs,
    ),
    _spec(
        "get_customer",
        "One customer by ID.",
        "GET",
        "/api/customers/:id",
        _get_customer,
        GetCustomerArgs,
    ),
    _spec(
        "search_customers",
        (
            "Search people by team, title, email, phone, location, status or join date. "
            "Filters combine and match substrings. "
        ),
        "GET",
        "/api/customers/search",
        _search_customers,
        SearchCustomersArgs,
    ),
    _spec(
        "create_customer",
        "Add one person.",
        "POST",
        "/api/customers",
        _create_customer,
        CreateCustomerArgs,
        mutating=True,
    ),
    _spec(
        "create_customers_bulk",
        "Add several people at once. Use instead of repeating create_customer.",
        "POST",
        "/api/customers/bulk",
        _create_customers_bulk,
        CreateManyArgs,
        mutating=True,
        success_label="Records created",
    ),
    _spec(
        "update_customer",
        "Change someone. match_name FINDS them; new_name is the value being set.",
        "PUT",
        "/api/customers/:id",
        _update_customer,
        UpdateCustomerArgs,
        mutating=True,
    ),
    _spec(
        "update_customers_bulk",
        (
            "Change many people at once - everyone, a team, or a named list. "
            "set_email accepts per-person placeholders like '{first}_{last}@domain.com'. "
            "Always use this rather than repeating update_customer."
        ),
        "PUT",
        "/api/customers/bulk",
        _update_customers_bulk,
        BulkUpdateArgs,
        mutating=True,
        success_label="Records updated",
    ),
    _spec(
        "delete_customer",
        "Delete someone. Soft - restorable via restore_customer.",
        "DELETE",
        "/api/customers/:id",
        _delete_customer,
        DeleteCustomerArgs,
        mutating=True,
        success_label="Moved to recycle bin",
    ),
    _spec(
        "restore_customer",
        "Undo a deletion. match_name searches the recycle bin directly.",
        "POST",
        "/api/customers/:id/restore",
        _restore_customer,
        RestoreCustomerArgs,
        mutating=True,
        success_label="Record restored",
    ),
    _spec(
        "add_note",
        "Save a note about someone.",
        "POST",
        "/api/customers/:id/notes",
        _add_note,
        AddNoteArgs,
        mutating=True,
        success_label="Note saved",
    ),
    _spec(
        "get_notes",
        "Read someone's notes.",
        "GET",
        "/api/customers/:id/notes",
        _get_notes,
        GetNotesArgs,
    ),
    _spec(
        "team_overview",
        "Headcount and team breakdown. Use for any 'how many people' question.",
        "GET",
        "/api/customers/stats",
        _team_overview,
        TeamOverviewArgs,
    ),
    _spec(
        "get_leave_requests",
        "List leave requests, pending by default. Rows carry the request ID.",
        "GET",
        "/api/leave",
        _get_leave_requests,
        GetLeaveArgs,
    ),
    _spec(
        "approve_leave",
        (
            "Approve pending leave. Pass match_name directly, no lookup first. Also writes "
            "attendance and status when it covers today. "
        ),
        "POST",
        "/api/leave/:id/approve",
        _approve_leave,
        DecideLeaveArgs,
        mutating=True,
        success_label="Leave approved",
    ),
    _spec(
        "reject_leave",
        "Reject pending leave. Reason required. Pass match_name directly.",
        "POST",
        "/api/leave/:id/reject",
        _reject_leave,
        RejectLeaveArgs,
        mutating=True,
        success_label="Leave rejected",
    ),
    _spec(
        "request_leave",
        "Log a new leave request. Starts pending.",
        "POST",
        "/api/leave",
        _request_leave,
        RequestLeaveArgs,
        mutating=True,
        success_label="Leave request logged",
    ),
    _spec(
        "mark_attendance",
        "Mark ONE person for a day. Re-marking corrects the record.",
        "POST",
        "/api/attendance",
        _mark_attendance,
        MarkAttendanceArgs,
        mutating=True,
        success_label="Attendance marked",
    ),
    _spec(
        "mark_team_attendance",
        "Mark a team or a named list. For 'everyone' use mark_bulk_attendance.",
        "POST",
        "/api/attendance/bulk",
        _mark_team_attendance,
        MarkTeamAttendanceArgs,
        mutating=True,
        success_label="Attendance marked",
    ),
    _spec(
        "mark_bulk_attendance",
        (
            "Mark EVERYONE (everyone=true). except_names handles 'everyone except X' - then "
            "mark_attendance separately for that person. "
        ),
        "POST",
        "/api/attendance/bulk",
        _mark_bulk_attendance,
        MarkBulkAttendanceArgs,
        mutating=True,
        success_label="Attendance marked",
    ),
    _spec(
        "get_attendance",
        "Read attendance by person, day, range, team or status.",
        "GET",
        "/api/attendance",
        _get_attendance,
        GetAttendanceArgs,
    ),
    _spec(
        "attendance_summary",
        "A day's counts plus who is unmarked. match_name gives one person's rate.",
        "GET",
        "/api/attendance/summary",
        _attendance_summary,
        AttendanceSummaryArgs,
    ),
    _spec(
        "employee_snapshot",
        (
            "Everything about one person in ONE call: profile, manager, reports, attendance, "
            "leave, tasks, notes. Use for 'tell me about X'. "
        ),
        "GET",
        "/api/customers/:id/snapshot",
        _employee_snapshot,
        SnapshotArgs,
    ),
    _spec(
        "create_task",
        "Create a task. Assign at creation with assignee_name.",
        "POST",
        "/api/work-tasks",
        _create_task,
        CreateTaskArgs,
        mutating=True,
        success_label="Task created",
    ),
    _spec(
        "assign_task",
        "Assign an existing task. Needs its ID.",
        "POST",
        "/api/work-tasks/:id/assign",
        _assign_task,
        AssignTaskArgs,
        mutating=True,
        success_label="Task assigned",
    ),
    _spec(
        "update_task",
        "Change a task. To finish one, use complete_task.",
        "PUT",
        "/api/work-tasks/:id",
        _update_task,
        UpdateTaskArgs,
        mutating=True,
        success_label="Task updated",
    ),
    _spec(
        "complete_task",
        "Mark a task done.",
        "POST",
        "/api/work-tasks/:id/complete",
        _complete_task,
        CompleteTaskArgs,
        mutating=True,
        success_label="Task completed",
    ),
    _spec(
        "list_tasks",
        "Find tasks by assignee, team, status, priority or deadline. Rows carry the ID.",
        "GET",
        "/api/work-tasks",
        _list_tasks,
        ListTasksArgs,
    ),
    _spec(
        "task_summary",
        "Workload totals for a person or team.",
        "GET",
        "/api/work-tasks/summary",
        _task_summary,
        TaskSummaryArgs,
    ),
    _spec(
        "search_sent_mail",
        "Search sent emails by recipient or text.",
        "GET",
        "/api/mail/sent",
        _search_sent_mail,
        SearchSentMailArgs,
    ),
    _spec(
        "draft_email",
        (
            "Draft an email for the user to approve. recipient_name is resolved from the "
            "records - never ask for an address. Drafts only, never sends. "
        ),
        "POST",
        "/api/mail/generate",
        _draft_email,
        DraftEmailArgs,
        success_label="Draft ready for your approval",
    ),
    _spec(
        "detect_workspace_anomalies",
        (
            "Scan the entire workspace for operational bottlenecks, overloaded staff, "
            "unassigned critical tasks, upcoming leave conflicts, and attendance issues."
        ),
        "GET",
        "/api/analytics/anomalies",
        _detect_workspace_anomalies,
        DetectAnomaliesArgs,
        success_label="Workspace anomaly scan complete",
    ),
    _spec(
        "generate_chart",
        (
            "Generate visual chart data (bar, donut, pie, line) for headcount, task status, "
            "task priority, attendance, leave, or meetings across teams."
        ),
        "GET",
        "/api/analytics/charts",
        _generate_chart,
        GenerateChartArgs,
        success_label="Chart generated",
    ),
    _spec(
        "schedule_meeting",
        (
            "Schedule a calendar meeting or sync with one or more colleagues. Resolves attendee "
            "names automatically."
        ),
        "POST",
        "/api/meetings",
        _schedule_meeting,
        ScheduleMeetingArgs,
        mutating=True,
        success_label="Meeting scheduled",
    ),
    _spec(
        "find_free_slots",
        (
            "Find open, available meeting slots for specified people on a given date by checking "
            "existing meetings, approved leaves, and work hours."
        ),
        "GET",
        "/api/meetings/slots",
        _find_free_slots,
        FindFreeSlotsArgs,
        success_label="Available slots checked",
    ),
    _spec(
        "list_meetings",
        "Find upcoming meetings and calendar events by team, date range, or attendee.",
        "GET",
        "/api/meetings",
        _list_meetings,
        ListMeetingsArgs,
    ),
    _spec(
        "cancel_meeting",
        "Cancel a scheduled meeting by ID.",
        "POST",
        "/api/meetings/:id/cancel",
        _cancel_meeting,
        CancelMeetingArgs,
        mutating=True,
        success_label="Meeting cancelled",
    ),
    _spec(
        "plan_project_sprint",
        (
            "Decompose a plain-English project goal into a full sprint of structured tasks, "
            "assign them across named team members, and create all tasks in one call. "
            "Returns the sprint plan with task list, priorities, and due dates."
        ),
        "POST",
        "/api/work-tasks/sprint",
        _plan_sprint,
        PlanSprintArgs,
        mutating=True,
        success_label="Sprint planned and tasks created",
    ),
    _spec(
        "rebalance_team_workload",
        (
            "Detect overloaded team members and redistribute their medium/low priority "
            "open tasks to teammates with lighter loads. Reports what moved and to whom."
        ),
        "POST",
        "/api/work-tasks/rebalance",
        _rebalance_team_workload,
        RebalanceWorkloadArgs,
        mutating=True,
        success_label="Workload rebalanced",
    ),
    _spec(
        "generate_daily_standup_digest",
        (
            "Generate a 360° morning standup briefing for today: attendance counts, "
            "urgent/overdue tasks, scheduled meetings, pending leave requests, and "
            "critical workspace alerts. Use for 'morning digest', 'daily briefing', "
            "'what's happening today', 'standup', or 'today's overview'."
        ),
        "GET",
        "/api/analytics/standup",
        _generate_daily_standup_digest,
        DailyStandupArgs,
        success_label="Standup digest ready",
    ),
    _spec(
        "request_clarification",
        "Ask for a missing required detail. Never guess.",
        "-",
        "-",
        _request_clarification,
        ClarifyArgs,
        control=True,
    ),
    _spec(
        "report_unsupported",
        "Only for requests unrelated to this system.",
        "-",
        "-",
        _report_unsupported,
        UnsupportedArgs,
        control=True,
    ),
]

REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in _SPECS}

# What gets bound to the model.
BOUND_TOOLS = [spec.tool for spec in _SPECS]


def get_spec(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def list_public_tools() -> list[dict[str, Any]]:
    """Tool metadata for the UI's Settings panel. Control tools are internal."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "method": spec.method,
            "endpoint": spec.endpoint,
            "parameters": spec.tool.args_schema.model_json_schema().get("properties", {}),
        }
        for spec in _SPECS
        if not spec.control
    ]


def execute(spec: ToolSpec, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Run a tool and log it to api_activity. Returns (result, duration_ms).

    Raises ApiError for anything the caller is allowed to see.
    """
    started = time.perf_counter()
    status_code = 200
    try:
        result = spec.tool.invoke(args)
        return result, int((time.perf_counter() - started) * 1000)
    except ApiError as exc:
        status_code = exc.status_code
        raise
    except Exception as exc:  # noqa: BLE001 - normalised into a safe ApiError
        status_code = 500
        raise ApiError(500, f"The {spec.name} tool failed to run.") from exc
    finally:
        if not spec.control:
            task_service.log_activity(
                method=spec.method,
                endpoint=spec.endpoint,
                status_code=status_code,
                duration_ms=int((time.perf_counter() - started) * 1000),
                source="agent",
            )
