from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..config import settings
from ..errors import ApiError
from ..ratelimit import rate_limit
from ..schemas import AttendanceMark
from ..security import require_admin
from ..services import attendance as service

router = APIRouter(
    prefix="/api/attendance",
    tags=["attendance"],
    dependencies=[Depends(rate_limit("customers", settings.customer_rate_per_min))],
)


@router.get("")
def list_records(
    customer_id: int | None = None,
    day: str | None = None,
    since: str | None = None,
    until: str | None = None,
    status: str | None = None,
    team: str | None = None,
    limit: int = Query(default=200, gt=0, le=500),
):
    return {
        "success": True,
        "data": service.list_records(
            customer_id=customer_id,
            day=day,
            since=since,
            until=until,
            status=status,
            team=team,
            limit=limit,
        ),
    }


@router.get("/summary")
def summary(day: str | None = None):
    return {"success": True, "data": service.day_summary(day)}


@router.post("", dependencies=[Depends(require_admin)])
def mark(payload: AttendanceMark):
    record = service.mark(
        payload.customer_id,
        payload.status,
        payload.day,
        note=payload.note,
        marked_by="you",
    )
    return {"success": True, "data": record, "message": "Attendance saved."}


@router.post("/bulk", dependencies=[Depends(require_admin)])
def mark_bulk(payload: list[AttendanceMark]):
    if not payload:
        raise ApiError(400, "Provide at least one record.")
    if len(payload) > 200:
        raise ApiError(400, "At most 200 records per request.")
    records = [
        service.mark(item.customer_id, item.status, item.day, note=item.note, marked_by="you")
        for item in payload
    ]
    return {"success": True, "data": records, "message": f"{len(records)} record(s) saved."}
