"""Work assigned to people.

Mounted at /api/work-tasks, deliberately not /api/tasks - that path is the agent's
own run history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..config import settings
from ..errors import ApiError
from ..ratelimit import rate_limit
from ..schemas import WorkTaskCreate, WorkTaskUpdate
from ..security import require_admin
from ..services import work_tasks as service

router = APIRouter(
    prefix="/api/work-tasks",
    tags=["work tasks"],
    dependencies=[Depends(rate_limit("customers", settings.customer_rate_per_min))],
)

TaskId = Path(gt=0, description="Positive integer task ID")


@router.get("")
def list_tasks(
    assignee_id: int | None = None,
    team: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    open_only: bool = False,
    overdue_only: bool = False,
    unassigned: bool = False,
    limit: int = Query(default=100, gt=0, le=200),
):
    return {
        "success": True,
        "data": service.list_tasks(
            assignee_id=assignee_id,
            team=team,
            status=status,
            priority=priority,
            open_only=open_only,
            overdue_only=overdue_only,
            unassigned=unassigned,
            limit=limit,
        ),
        "summary": service.summary(),
    }


# Declared before /{task_id} so "summary" is never parsed as an ID.
@router.get("/summary")
def summary(assignee_id: int | None = None, team: str | None = None):
    return {"success": True, "data": service.summary(assignee_id=assignee_id, team=team)}


@router.get("/{task_id}")
def get_task(task_id: int = TaskId):
    found = service.get_task(task_id)
    if found is None:
        raise ApiError(404, "Task not found")
    return {"success": True, "data": found}


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_task(payload: WorkTaskCreate):
    created = service.create(**payload.model_dump(exclude_none=True), created_by="you")
    return {"success": True, "data": created}


@router.put("/{task_id}", dependencies=[Depends(require_admin)])
@router.patch("/{task_id}", dependencies=[Depends(require_admin)])
def update_task(payload: WorkTaskUpdate, task_id: int = TaskId):
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not fields:
        raise ApiError(400, "At least one field is required")
    updated = service.update(task_id, fields)
    if updated is None:
        raise ApiError(404, "Task not found")
    return {"success": True, "data": updated}


@router.post("/{task_id}/complete", dependencies=[Depends(require_admin)])
def complete_task(task_id: int = TaskId):
    existing = service.get_task(task_id)
    if existing is None:
        raise ApiError(404, "Task not found")
    if existing["status"] == "done":
        raise ApiError(409, "That task is already complete.")
    return {"success": True, "data": service.update(task_id, {"status": "done"})}


@router.post("/{task_id}/assign", dependencies=[Depends(require_admin)])
def assign_task(payload: WorkTaskUpdate, task_id: int = TaskId):
    if payload.assignee_id is None and not payload.team:
        raise ApiError(400, "Provide an assignee_id or a team.")
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    updated = service.update(task_id, fields)
    if updated is None:
        raise ApiError(404, "Task not found")
    return {"success": True, "data": updated}


@router.delete("/{task_id}", dependencies=[Depends(require_admin)])
def delete_task(task_id: int = TaskId):
    from ..db import connect

    with connect() as conn:
        removed = conn.execute("DELETE FROM work_tasks WHERE id = ?", (task_id,)).rowcount
    if not removed:
        raise ApiError(404, "Task not found")
    return {"success": True, "message": "Task deleted."}
