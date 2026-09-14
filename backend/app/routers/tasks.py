from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..errors import ApiError
from ..security import require_admin
from ..services import tasks as service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

TaskId = Path(gt=0, description="Positive integer task ID")


@router.get("")
def list_tasks(
    limit: int = Query(default=50, gt=0, le=200),
    offset: int = Query(default=0, ge=0),
):
    return {
        "success": True,
        "data": service.list_tasks(limit=limit, offset=offset),
        "total": service.count_tasks(),
    }


# Declared before /{task_id} so "activity" is never parsed as an ID.
@router.get("/activity/recent")
def recent_activity(limit: int = Query(default=30, gt=0, le=200)):
    return {"success": True, "data": service.recent_activity(limit=limit)}


@router.get("/{task_id}")
def get_task(task_id: int = TaskId):
    task = service.get_task(task_id)
    if task is None:
        raise ApiError(404, "Task not found")
    return {"success": True, "data": task}


@router.delete("/{task_id}", dependencies=[Depends(require_admin)])
def delete_task(task_id: int = TaskId):
    if not service.delete_task(task_id):
        raise ApiError(404, "Task not found")
    return {"success": True, "message": "Task history deleted."}
