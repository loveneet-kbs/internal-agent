"""Request models. `extra="forbid"` turns unknown fields into a 400 rather than
silently ignoring them, which is what the previous backend's allow-list did.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Same shape the frontend enforces. Kept as a regex rather than pulling in
# `email-validator` for one field.
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]


def validate_email(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ValueError("must be a valid email address")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
IsoDate = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10)]
STATUSES = ("active", "on_leave", "alumni")


def validate_status(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    if value not in STATUSES:
        raise ValueError(f"must be one of: {', '.join(STATUSES)}")
    return value


class CustomerCreate(Strict):
    name: Name
    email: str
    phone: Phone | None = None
    team: Short | None = None
    title: Short | None = None
    location: Short | None = None
    status: str | None = None
    joined_at: IsoDate | None = None

    _check_email = field_validator("email")(validate_email)
    _check_status = field_validator("status")(validate_status)


class CustomerUpdate(Strict):
    name: Name | None = None
    email: str | None = None
    phone: Phone | None = None
    team: Short | None = None
    title: Short | None = None
    location: Short | None = None
    status: str | None = None
    joined_at: IsoDate | None = None

    _check_status = field_validator("status")(validate_status)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else validate_email(value)

    def changed_fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True)


class BulkUpdate(Strict):
    everyone: bool = False
    team_filter: Short | None = None
    email: Short | None = None
    team: Short | None = None
    title: Short | None = None
    location: Short | None = None
    status: str | None = None

    _check_status = field_validator("status")(validate_status)


class WorkTaskCreate(Strict):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    priority: Short = "medium"
    status: Short = "todo"
    assignee_id: int | None = None
    team: Short | None = None
    due_date: IsoDate | None = None


class WorkTaskUpdate(Strict):
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    priority: Short | None = None
    status: Short | None = None
    assignee_id: int | None = None
    team: Short | None = None
    due_date: IsoDate | None = None


class AttendanceMark(Strict):
    customer_id: int = Field(gt=0)
    status: Short
    day: IsoDate | None = None
    note: Annotated[str, StringConstraints(max_length=300)] | None = None


class LeaveCreate(Strict):
    customer_id: int = Field(gt=0)
    start_date: IsoDate
    end_date: IsoDate
    leave_type: Short = "annual"
    reason: Annotated[str, StringConstraints(max_length=500)] | None = None


class LeaveDecision(Strict):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class NoteCreate(Strict):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    author: Short | None = None


class AgentRunRequest(Strict):
    prompt: str = Field(min_length=1)


class MailDraftRequest(Strict):
    recipient: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    purpose: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    details: Annotated[str, StringConstraints(max_length=3000)] = ""
    tone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] = "professional"


class MailSendRequest(BaseModel):
    """`from` never becomes the envelope sender - see services/mail.py. It is only
    used as Reply-To, and may be omitted entirely (the approval card does)."""

    from_: str | None = Field(default=None, alias="from")
    to: str
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    @field_validator("from_")
    @classmethod
    def _from(cls, value: str | None) -> str | None:
        return None if value in (None, "") else validate_email(value)

    _check_to = field_validator("to")(validate_email)


class Step(BaseModel):
    label: str
    status: Literal[
        "completed", "running", "failed", "needs_information", "unsupported", "pending"
    ]
    detail: str | None = None
