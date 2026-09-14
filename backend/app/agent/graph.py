"""The LangGraph agent.

    START -> classify -> validate -> execute -+-> classify   (loop, up to MAX_STEPS)
                  |          |                |
                  |          +--> respond ----+--> END
                  +--> END

The agent runs a real tool loop: after each tool executes, its result is fed back as
a ToolMessage and the model decides whether more work is needed. That lets one prompt
chain several actions - "add Aisha and email her a welcome" creates the record, reads
back the new row, then drafts to that address.

The model's reply is never trusted directly. `validate` re-checks every chosen name
against the local registry and re-validates the arguments against that tool's schema
before `execute` runs. The model picks a name; it never picks behaviour.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from ..errors import ApiError
from . import routing
from . import tools as tool_registry
from .llm import get_llm

log = logging.getLogger("app.agent")

# Hard ceiling on tool executions per prompt. Prevents a loop from running away and
# bounds the blast radius of a chain that goes wrong.
MAX_STEPS = 5

INTENT_BY_TOOL = {
    "get_customers": "list_customers",
    "get_customer": "fetch_customer",
    "create_customer": "create_customer",
    "update_customer": "update_customer",
    "update_customers_bulk": "update_customer",
    "delete_customer": "delete_customer",
    "draft_email": "draft_email",
    "get_leave_requests": "list_leave",
    "approve_leave": "approve_leave",
    "reject_leave": "reject_leave",
    "request_leave": "request_leave",
    "mark_attendance": "mark_attendance",
    "mark_team_attendance": "mark_attendance",
    "mark_bulk_attendance": "mark_attendance",
    "get_attendance": "list_attendance",
    "attendance_summary": "attendance_summary",
    "employee_snapshot": "employee_snapshot",
    "create_task": "create_task",
    "assign_task": "assign_task",
    "update_task": "update_task",
    "complete_task": "complete_task",
    "list_tasks": "list_tasks",
    "task_summary": "task_summary",
    "detect_workspace_anomalies": "detect_anomalies",
    "generate_chart": "generate_chart",
    "schedule_meeting": "schedule_meeting",
    "find_free_slots": "find_slots",
    "list_meetings": "list_meetings",
    "cancel_meeting": "cancel_meeting",
    "plan_project_sprint": "plan_sprint",
    "rebalance_team_workload": "rebalance_workload",
    "generate_daily_standup_digest": "standup_digest",
    "request_clarification": "needs_information",
    "report_unsupported": "unsupported",
}

SYSTEM_PROMPT = """You select tools for a workspace operations system (employees, leave,
attendance, tasks, calendar meetings, charts, anomalies, email). "customer", "employee",
"staff", "person" all mean the same records - never decline over wording.

Call ONE tool per turn. Read its result, then decide what is next. When the request
is fully done, reply with a short plain sentence and no tool call.

Rules:
1. Only call tools from the list. Never write SQL or code.
2. Take values from the user and from earlier results. Never invent an email,
   phone, or ID. Passing a NAME is not inventing - tools resolve names themselves,
   so never look someone up just to get their ID.
3. update_customer: match_name FINDS the person, new_name is the new value.
   For MANY people use update_customers_bulk - never loop update_customer.
   Values may contain per-person placeholders: {first} {last} {full} {initials}.
   "everyone's email as firstname_lastname@x.com" is one call with
   everyone=true and set_email="{first}_{last}@x.com" - pass the template
   literally, never expand it per person yourself.
4. draft_email drafts only; the user sends it. Put every concrete fact the user
   gave into `details`. Never claim you sent anything.
5. approve_leave / reject_leave take match_name directly - no lookup first.
   Rejecting needs a reason. Approving also writes attendance and status, so do
   not do those by hand.
6. Attendance: mark_attendance = one person, mark_team_attendance = a team or
   named list, mark_bulk_attendance(everyone=true) = everyone. Never loop.
   "Everyone present except X who is absent" = mark_bulk_attendance with
   except_names, then mark_attendance for X.
7. employee_snapshot answers "tell me about X" in one call. Never assemble that
   picture from several tools.
8. Tasks: create_task can assign at the same time. assign/update/complete need the
   task ID from list_tasks.
9. Anomalies & Curiosity: detect_workspace_anomalies scans for work imbalances,
   unassigned urgent tasks, bottlenecked people, and leave collisions across the workspace.
10. Visual Charts: generate_chart generates visual analytics for tasks, headcount,
    workload, attendance, leave, or meetings. metric can be tasks_by_status,
    tasks_by_priority, headcount_by_team, workload_by_team, attendance_breakdown,
    leave_by_type, meetings_by_team. chart_type can be bar, donut, pie, line.
11. Calendar & Meetings: schedule_meeting schedules meetings (resolving attendee names
    directly). find_free_slots checks working hours, active leaves, and calendar conflicts
    to find open times on a date. list_meetings queries scheduled events.
12. If asked to CHANGE something, you must call a tool that changes it. Reading is
    not doing. Never finish a change request having only looked things up.
13. Do only what was asked. Never delete, overwrite, or decide leave that was not
    requested.
14. Never repeat a call with the same arguments.
15. Attendance and leave rows already carry the person's name; their `id` is the
    RECORD id, not the person's.
16. Missing a required detail? request_clarification, asking for exactly that.
17. report_unsupported is only for things this system does not do at all - not for
    "nothing found", which is a valid answer.
"""


class AgentState(TypedDict, total=False):
    prompt: str
    messages: list[Any]
    bound_tools: list[Any]
    executed: list[dict[str, Any]]
    tool_name: str | None
    tool_args: dict[str, Any]
    intent: str
    status: str
    result: dict[str, Any] | None
    error: str | None
    steps: list[dict[str, Any]]
    duration_ms: int
    summary: str


def _step(label: str, status: str, detail: str | None = None) -> dict[str, Any]:
    step: dict[str, Any] = {"label": label, "status": status}
    if detail:
        step["detail"] = detail
    return step


def _rate_limit_message(exc: Exception) -> str | None:
    """Turn a Groq 429 into something actionable.

    Reporting a quota ceiling as "could not be reached" sends people hunting for a
    network or key problem that does not exist.
    """
    text = str(exc)
    if "429" not in text and "rate_limit" not in text.lower():
        return None

    # Groq reports exactly how long to wait; quoting it beats guessing, and the
    # daily allowance rolls rather than resetting at a fixed hour.
    import re

    retry = re.search(r"try again in ([0-9hms.]+?)\.?(?:\s|$|\"|')", text)
    wait = f" Try again in {retry.group(1)}." if retry else ""

    if "per day" in text or "TPD" in text:
        return (
            f"The daily Groq token quota for this key is used up.{wait} "
            "Raise the limit at console.groq.com/settings/billing."
        )
    return f"The AI service is rate limited right now.{wait or ' Wait a moment and try again.'}"


def _is_empty_generation(exc: Exception) -> bool:
    """Groq returns 400 `tool_use_failed` when tool_choice forces a call but the
    model emits nothing. It is transient - the same prompt usually succeeds on a
    retry - so it must not surface as a failed task."""
    return "tool_use_failed" in str(exc)


def _invoke_model(llm, messages, attempts: int = 3):
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001
            if not _is_empty_generation(exc):
                raise
            last = exc
            log.warning("Groq returned an empty generation (attempt %d/%d)", attempt, attempts)
    assert last is not None
    raise last


def _text_of(message: AIMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return " ".join(part for part in parts if part).strip()
    return ""


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def classify(state: AgentState) -> AgentState:
    """Ask the model what to do next. Emits no side effects."""
    executed = state.get("executed") or []
    first_turn = not executed

    # The opening turn must choose a tool, which is what drives the clarification
    # and unsupported paths. Later turns may decline, and that is how the run ends.
    bound = state.get("bound_tools") or tool_registry.BOUND_TOOLS
    llm = get_llm(temperature=0.0).bind_tools(
        bound, tool_choice="any" if first_turn else "auto"
    )

    if len(executed) >= MAX_STEPS:
        return {
            **state,
            "status": "completed" if executed else "failed",
            "summary": f"Stopped after {MAX_STEPS} steps.",
            "steps": state["steps"]
            + [_step(f"Step limit reached ({MAX_STEPS})", "completed")],
        }

    try:
        reply = _invoke_model(llm, state["messages"])
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("Groq call failed")
        throttled = _rate_limit_message(exc)
        if throttled:
            raise ApiError(429, throttled) from exc
        if _is_empty_generation(exc):
            return {
                **state,
                "status": "needs_information",
                "error": (
                    "I could not work out which action you meant. Try rephrasing - "
                    'for example "email Priya about the design review".'
                ),
                "steps": state["steps"]
                + [_step("Could not determine an action", "needs_information")],
            }
        raise ApiError(502, "The AI service could not be reached. Please try again.") from exc

    calls = getattr(reply, "tool_calls", None) or []

    if not calls:
        text = _text_of(reply)
        if first_turn:
            return {
                **state,
                "status": "unsupported",
                "error": text or "The AI did not select a tool for this request.",
                "steps": state["steps"] + [_step("No tool selected", "failed")],
            }
        # Later turn with no tool call: the model considers the work finished.
        return {**state, "status": "completed", "summary": text, "messages": [*state["messages"], reply]}

    if len(calls) > 1:
        # One tool per turn keeps validation, the step trace, and error attribution
        # unambiguous. Extra calls are not silently dropped - the model is told.
        log.info("Model proposed %d calls; taking the first and continuing", len(calls))

    call = calls[0]
    name = call.get("name")
    args = call.get("args") or {}

    # A model that re-requests a result it already has would loop to the step cap
    # and bill an LLM round trip each time. Treat the repeat as "done".
    if any(
        step["tool"] == name and step["args"] == args for step in executed
    ):
        log.info("Model repeated %s with identical arguments; ending the run", name)
        return {
            **state,
            "status": "completed",
            "summary": "",
            "messages": [*state["messages"], reply],
        }

    label = "Intent detected" if first_turn else "Deciding next step"
    return {
        **state,
        "messages": [*state["messages"], reply],
        "tool_name": name,
        "tool_args": args,
        "intent": state.get("intent") or INTENT_BY_TOOL.get(name, name or "unknown"),
        "steps": state["steps"]
        + [_step(label, "completed", INTENT_BY_TOOL.get(name, name))],
    }


def validate(state: AgentState) -> AgentState:
    """Re-check the model's choice against the local registry. The guardrail."""
    name = state.get("tool_name")
    spec = tool_registry.get_spec(name or "")

    if spec is None:
        return {
            **state,
            "status": "failed",
            "error": f'Unknown tool "{name}". This tool does not exist in the registry.',
            "steps": state["steps"]
            + [_step("Tool validation failed", "failed", f"unknown tool: {name}")],
        }

    try:
        coerced = spec.tool.args_schema.model_validate(state.get("tool_args") or {})
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first.get("loc", ()))
        detail = f"{field}: {first.get('msg')}" if field else str(first.get("msg"))
        return {
            **state,
            "status": "failed",
            "error": f"Invalid arguments for {name} - {detail}",
            "steps": state["steps"] + [_step("Tool validation failed", "failed", detail)],
        }

    steps = state["steps"] + [_step(f"Tool selected: {name}", "completed")]
    if not spec.control:
        steps.append(_step(f"Calling {spec.method} {spec.endpoint}", "running"))

    return {**state, "tool_args": coerced.model_dump(exclude_none=True), "steps": steps}


def execute(state: AgentState) -> AgentState:
    """Run the validated tool. This is where the database actually changes."""
    spec = tool_registry.get_spec(state["tool_name"] or "")
    assert spec is not None  # validate() guarantees this

    steps = list(state["steps"])
    args = state.get("tool_args") or {}
    call_id = _last_call_id(state)

    try:
        result, duration_ms = tool_registry.execute(spec, args)
    except ApiError as exc:
        steps[-1] = _step(f"Calling {spec.method} {spec.endpoint}", "failed")
        steps.append(_step("Operation failed", "failed", exc.message))
        return {**state, "status": "failed", "error": exc.message, "steps": steps}

    steps[-1] = _step(f"Calling {spec.method} {spec.endpoint}", "completed")
    steps.append(_step(spec.success_label, "completed"))

    executed = [
        *(state.get("executed") or []),
        {"tool": spec.name, "args": args, "result": result, "duration_ms": duration_ms},
    ]

    return {
        **state,
        "executed": executed,
        "result": result,
        "error": None,
        "duration_ms": (state.get("duration_ms") or 0) + duration_ms,
        "steps": steps,
        # Feed the result back so the model can use it in the next decision.
        "messages": [
            *state["messages"],
            ToolMessage(content=_summarise(result), tool_call_id=call_id),
        ],
    }


def respond(state: AgentState) -> AgentState:
    """Handle the two control tools: ask for a detail, or decline the request."""
    name = state["tool_name"]
    args = state.get("tool_args") or {}
    message = args.get("question") or args.get("reason") or ""

    if name == "request_clarification":
        return {
            **state,
            "status": "needs_information",
            "error": message,
            "steps": state["steps"]
            + [_step("Needs more information", "needs_information", message)],
        }

    return {
        **state,
        "status": "unsupported",
        "error": message or "No available tool matches this request.",
        "steps": state["steps"] + [_step("No matching tool", "unsupported", message)],
    }


def _last_call_id(state: AgentState) -> str:
    for message in reversed(state.get("messages") or []):
        calls = getattr(message, "tool_calls", None) or []
        if calls:
            return calls[0].get("id") or "call"
    return "call"


# Fields worth feeding back, in priority order. Keeping only "id" meant an
# attendance row came back as {"id": 131} - a bare number the model mistook for a
# customer ID and then tried to look up. The summary has to carry enough to act on.
_KEEP = (
    "id",
    "customer_id",
    "person",
    "name",
    "email",
    "day",
    "status",
    "leave_type",
    "start_date",
    "end_date",
    "days",
    "team",
    "title",
    "subject",
    "recipient",
)


def _summarise(result: dict[str, Any]) -> str:
    """Compact a tool result for the model's next turn - full rows would bloat context."""
    import json

    message = result.get("message", "")
    data = result.get("data")

    if isinstance(data, list):
        preview = [
            {key: row[key] for key in _KEEP if key in row and row[key] is not None}
            for row in data[:10]
            if isinstance(row, dict)
        ]
        more = f" (+{len(data) - 10} more)" if len(data) > 10 else ""
        return f"{message} {json.dumps(preview)}{more}"

    if isinstance(data, dict):
        if data.get("kind") == "email_draft":
            return f"{message} Draft prepared for {data.get('to')} and shown to the user."
        keep = {key: data[key] for key in _KEEP if key in data and data[key] is not None}
        return f"{message} {json.dumps(keep)}"

    return message or "Done."


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def _after_classify(state: AgentState) -> Literal["validate", "__end__"]:
    return END if state.get("status") else "validate"


def _after_validate(state: AgentState) -> Literal["execute", "respond", "__end__"]:
    if state.get("status"):
        return END
    spec = tool_registry.get_spec(state.get("tool_name") or "")
    return "respond" if spec and spec.control else "execute"


def _after_execute(state: AgentState) -> Literal["classify", "__end__"]:
    """Loop back for another step unless the run already failed or hit the cap."""
    if state.get("status") == "failed":
        return END
    if len(state.get("executed") or []) >= MAX_STEPS:
        return END
    return "classify"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify", classify)
    graph.add_node("validate", validate)
    graph.add_node("execute", execute)
    graph.add_node("respond", respond)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", _after_classify, {"validate": "validate", END: END})
    graph.add_conditional_edges(
        "validate", _after_validate, {"execute": "execute", "respond": "respond", END: END}
    )
    graph.add_conditional_edges("execute", _after_execute, {"classify": "classify", END: END})
    graph.add_edge("respond", END)

    return graph.compile()


_COMPILED = None


def get_graph():
    """Compile once, reuse. Compilation is pure structure, so this is safe to cache."""
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED


def run(prompt: str) -> AgentState:
    initial: AgentState = {
        "prompt": prompt,
        "messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)],
        # Chosen once and reused for every turn, so a follow-up step cannot find a
        # tool missing halfway through a chain.
        "bound_tools": routing.select(prompt),
        "executed": [],
        "tool_name": None,
        "tool_args": {},
        "intent": "",
        "status": "",
        "result": None,
        "error": None,
        "steps": [_step("Prompt received", "completed")],
        "duration_ms": 0,
        "summary": "",
    }
    # recursion_limit bounds LangGraph's own node visits; MAX_STEPS bounds tool runs.
    final = get_graph().invoke(initial, {"recursion_limit": MAX_STEPS * 4 + 10})

    if final.get("executed") and not final.get("status"):
        final["status"] = "completed"
    if final.get("status") == "completed" and final.get("steps"):
        final["steps"] = [*final["steps"], _step("Task completed", "completed")]
    return final
