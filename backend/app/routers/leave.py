from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..config import settings
from ..errors import ApiError
from ..ratelimit import rate_limit
from ..schemas import LeaveCreate, LeaveDecision
from ..security import require_admin
from ..services import leave as service

router = APIRouter(
    prefix="/api/leave",
    tags=["leave"],
    dependencies=[Depends(rate_limit("customers", settings.customer_rate_per_min))],
)

LeaveId = Path(gt=0, description="Positive integer leave request ID")


@router.get("")
def list_requests(
    customer_id: int | None = None,
    status: str | None = None,
    leave_type: str | None = None,
    team: str | None = None,
    limit: int = Query(default=50, gt=0, le=200),
):
    return {
        "success": True,
        "data": service.list_requests(
            customer_id=customer_id,
            status=status,
            leave_type=leave_type,
            team=team,
            limit=limit,
        ),
        "summary": service.summary(),
    }


@router.get("/{request_id}")
def get_request(request_id: int = LeaveId):
    found = service.get_request(request_id)
    if found is None:
        raise ApiError(404, "Leave request not found")
    return {"success": True, "data": found}


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_request(payload: LeaveCreate):
    created = service.create_request(
        customer_id=payload.customer_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        leave_type=payload.leave_type,
        reason=payload.reason,
    )
    return {"success": True, "data": created}


@router.post("/{request_id}/approve", dependencies=[Depends(require_admin)])
def approve(payload: LeaveDecision | None = None, request_id: int = LeaveId):
    outcome = service.decide(
        request_id=request_id,
        approve=True,
        note=payload.note if payload else None,
        decided_by="you",
    )
    return {
        "success": True,
        "data": outcome["request"],
        "message": "Leave approved."
        + (" Marked on leave." if outcome["status_changed"] else ""),
    }


@router.post("/{request_id}/reject", dependencies=[Depends(require_admin)])
def reject(payload: LeaveDecision, request_id: int = LeaveId):
    if not (payload.note or "").strip():
        raise ApiError(400, "A reason is required to reject a leave request.")
    outcome = service.decide(
        request_id=request_id, approve=False, note=payload.note, decided_by="you"
    )
    return {"success": True, "data": outcome["request"], "message": "Leave rejected."}
