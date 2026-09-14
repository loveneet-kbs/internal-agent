"""Wires the LangGraph run to the task-history record the UI reads."""

from __future__ import annotations

import json
from typing import Any

from ..errors import ApiError
from ..services import tasks as task_service
from .graph import run as run_graph


def run_agent(prompt: str) -> dict[str, Any]:
    task = task_service.create_task(prompt)

    try:
        state = run_graph(prompt)
    except ApiError as exc:
        updated = task_service.update_task(task["id"], status="failed", error=exc.message)
        return {
            "success": False,
            "task": updated or task,
            "steps": [
                {"label": "Prompt received", "status": "completed"},
                {"label": "Intent detection failed", "status": "failed", "detail": exc.message},
            ],
            "result": None,
        }

    status = state.get("status") or "failed"
    executed = state.get("executed") or []
    result = state.get("result")

    updates: dict[str, Any] = {
        "intent": state.get("intent"),
        "status": status,
        "error": state.get("error"),
        # Every call the run made, in order - not just the last one.
        "parameters": json.dumps([step["args"] for step in executed] or state.get("tool_args") or {}),
        "result": json.dumps(result) if result is not None else None,
        "duration_ms": state.get("duration_ms") or 0,
    }

    from .tools import get_spec

    if executed:
        # History shows the whole chain; method/endpoint track the final call.
        updates["tool_name"] = ", ".join(step["tool"] for step in executed)
        last = get_spec(executed[-1]["tool"])
        if last is not None:
            updates["method"] = last.method
            updates["endpoint"] = last.endpoint
    else:
        # Control tools are not real endpoints, so they leave method/endpoint blank.
        spec = get_spec(state.get("tool_name") or "")
        if spec is not None and not spec.control:
            updates["tool_name"] = spec.name
            updates["method"] = spec.method
            updates["endpoint"] = spec.endpoint

    updated = task_service.update_task(task["id"], **updates)

    return {
        "success": status == "completed",
        "task": updated or task,
        "steps": state.get("steps") or [],
        "result": result,
        "summary": state.get("summary") or "",
        # Every step's own result, not just the last one. A chain like
        # "who is on leave, then email X" produces a list AND a draft, and the UI
        # needs both - previously only the final result reached the client.
        "executed": [
            {
                "tool": step["tool"],
                "args": step["args"],
                "duration_ms": step["duration_ms"],
                "result": step["result"],
            }
            for step in executed
        ],
    }
