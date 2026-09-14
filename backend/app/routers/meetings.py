"""Meetings and calendar routes."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..ratelimit import rate_limit
from ..security import require_admin
from ..services import meetings as service

router = APIRouter(
    prefix="/api/meetings",
    tags=["meetings"],
    dependencies=[Depends(rate_limit("customers", settings.customer_rate_per_min))],
)

MeetingId = Path(gt=0, description="Positive integer meeting ID")


class MeetingCreatePayload(BaseModel):
    title: str = Field(min_length=1)
    start_time: str
    end_time: str | None = None
    duration_minutes: int = 30
    host_id: int | None = None
    host_name: str | None = None
    attendees: list[Any] | None = None
    team: str | None = None
    location_or_link: str | None = None
    description: str | None = None


class CancelPayload(BaseModel):
    reason: str | None = None


@router.get("")
def list_meetings(
    team: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    attendee_name: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, gt=0, le=200),
):
    return {
        "success": True,
        "data": service.list_meetings(
            team=team,
            start_date=start_date,
            end_date=end_date,
            attendee_name=attendee_name,
            status=status,
            limit=limit,
        ),
    }


@router.get("/slots")
def find_slots(
    attendees: str = Query(description="Comma-separated names or IDs"),
    date: str = Query(description="Target date YYYY-MM-DD"),
    duration_minutes: int = Query(default=30, gt=0, le=240),
):
    attendee_list = [a.strip() for a in attendees.split(",") if a.strip()]
    return {
        "success": True,
        "data": service.find_free_slots(
            attendees=attendee_list,
            target_date=date,
            duration_minutes=duration_minutes,
        ),
    }


@router.get("/{meeting_id}")
def get_meeting(meeting_id: int = MeetingId):
    return {"success": True, "data": service.get_meeting(meeting_id)}


@router.post("", dependencies=[Depends(require_admin)])
def create_meeting(payload: MeetingCreatePayload):
    return {
        "success": True,
        "data": service.create_meeting(
            title=payload.title,
            start_time=payload.start_time,
            end_time=payload.end_time,
            duration_minutes=payload.duration_minutes,
            host_id=payload.host_id,
            host_name=payload.host_name,
            attendees=payload.attendees,
            team=payload.team,
            location_or_link=payload.location_or_link,
            description=payload.description,
        ),
    }


@router.post("/{meeting_id}/cancel", dependencies=[Depends(require_admin)])
def cancel_meeting(meeting_id: int = MeetingId, payload: CancelPayload | None = None):
    return {
        "success": True,
        "data": service.cancel_meeting(meeting_id, reason=payload.reason if payload else None),
    }
