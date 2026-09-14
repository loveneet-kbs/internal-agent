from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..config import settings
from ..errors import ApiError
from ..ratelimit import rate_limit
from ..schemas import BulkUpdate, CustomerCreate, CustomerUpdate, NoteCreate
from ..security import require_admin
from ..services import customers as service
from ..services import notes as note_service
from ..services import snapshot as snapshot_service

router = APIRouter(
    prefix="/api/customers",
    tags=["customers"],
    dependencies=[Depends(rate_limit("customers", settings.customer_rate_per_min))],
)

CustomerId = Path(gt=0, description="Positive integer customer ID")


@router.get("")
def list_customers(
    limit: int = Query(default=200, gt=0, le=500),
    offset: int = Query(default=0, ge=0),
):
    return {
        "success": True,
        "data": service.list_customers(limit=limit, offset=offset),
        "total": service.count_customers(),
    }


# Literal paths are declared before /{customer_id} so "search" and "stats" are
# never parsed as an ID.
@router.get("/search")
def search_customers(
    name: str | None = None,
    team: str | None = None,
    title: str | None = None,
    email_contains: str | None = None,
    phone_contains: str | None = None,
    location: str | None = None,
    status: str | None = None,
    joined_after: str | None = None,
    joined_before: str | None = None,
    sort: str = "id",
    descending: bool = True,
    limit: int = Query(default=50, gt=0, le=200),
):
    return {
        "success": True,
        "data": service.search(
            name=name,
            team=team,
            title=title,
            email_contains=email_contains,
            phone_contains=phone_contains,
            location=location,
            status=status,
            joined_after=joined_after,
            joined_before=joined_before,
            sort=sort,
            descending=descending,
            limit=limit,
        ),
    }


@router.get("/stats")
def stats():
    return {"success": True, "data": service.stats()}


@router.get("/deleted")
def recycle_bin(limit: int = Query(default=50, gt=0, le=200)):
    return {"success": True, "data": service.list_deleted(limit=limit)}


@router.get("/{customer_id}/snapshot")
def snapshot(customer_id: int = CustomerId):
    """Profile, manager, attendance, leave, tasks and notes in one read."""
    data = snapshot_service.build(customer_id)
    return {"success": True, "data": data, "message": snapshot_service.headline(data)}


@router.get("/{customer_id}")
def get_customer(customer_id: int = CustomerId):
    found = service.get_customer(customer_id)
    if found is None:
        raise ApiError(404, "Customer not found")
    return {
        "success": True,
        "data": {**found, "notes": note_service.list_notes(customer_id)},
    }


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_customer(payload: CustomerCreate):
    created = service.create_customer(**payload.model_dump(exclude_none=True))
    return {"success": True, "data": created}


@router.post("/bulk", status_code=201, dependencies=[Depends(require_admin)])
def create_bulk(payload: list[CustomerCreate]):
    if not payload:
        raise ApiError(400, "Provide at least one customer.")
    if len(payload) > 50:
        raise ApiError(400, "At most 50 customers per request.")
    outcome = service.create_many([p.model_dump(exclude_none=True) for p in payload])
    return {"success": True, **outcome}


@router.put("/bulk-update", dependencies=[Depends(require_admin)])
def update_bulk(payload: BulkUpdate):
    """Apply one change to many people. `email`/`title`/`location` may contain
    per-person placeholders such as {first}_{last}@domain.com."""
    people = (
        service.search(limit=500)
        if payload.everyone
        else service.search(team=payload.team_filter, limit=500)
    )
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    fields.pop("everyone", None)
    fields.pop("team_filter", None)
    outcome = service.update_many(people, fields)
    return {"success": True, **outcome}


@router.put("/{customer_id}", dependencies=[Depends(require_admin)])
@router.patch("/{customer_id}", dependencies=[Depends(require_admin)])
def update_customer(payload: CustomerUpdate, customer_id: int = CustomerId):
    fields = payload.changed_fields()
    if not fields:
        raise ApiError(400, "At least one field is required")
    updated = service.update_customer(customer_id, fields)
    if updated is None:
        raise ApiError(404, "Customer not found")
    return {"success": True, "data": updated}


@router.delete("/{customer_id}", dependencies=[Depends(require_admin)])
def delete_customer(customer_id: int = CustomerId):
    """Soft delete - the row is recoverable via /restore."""
    deleted = service.delete_customer(customer_id)
    if deleted is None:
        raise ApiError(404, "Customer not found")
    return {"success": True, "data": deleted, "message": "Moved to the recycle bin."}


@router.post("/{customer_id}/restore", dependencies=[Depends(require_admin)])
def restore_customer(customer_id: int = CustomerId):
    restored = service.restore_customer(customer_id)
    if restored is None:
        raise ApiError(404, "No deleted customer with that ID.")
    return {"success": True, "data": restored, "message": "Customer restored."}


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
@router.get("/{customer_id}/notes")
def list_notes(customer_id: int = CustomerId):
    if service.get_customer(customer_id) is None:
        raise ApiError(404, "Customer not found")
    return {"success": True, "data": note_service.list_notes(customer_id)}


@router.post("/{customer_id}/notes", status_code=201, dependencies=[Depends(require_admin)])
def add_note(payload: NoteCreate, customer_id: int = CustomerId):
    note = note_service.add_note(customer_id, payload.body, author=payload.author or "you")
    return {"success": True, "data": note}


@router.delete("/{customer_id}/notes/{note_id}", dependencies=[Depends(require_admin)])
def delete_note(customer_id: int = CustomerId, note_id: int = Path(gt=0)):
    if not note_service.delete_note(note_id):
        raise ApiError(404, "Note not found")
    return {"success": True, "message": "Note deleted."}
