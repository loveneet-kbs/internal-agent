from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from ..agent.service import run_agent
from ..agent.tools import list_public_tools
from ..config import settings
from ..errors import ApiError
from ..ratelimit import rate_limit
from ..schemas import AgentRunRequest

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run", dependencies=[Depends(rate_limit("agent", settings.agent_rate_per_min))])
async def run(payload: AgentRunRequest):
    prompt = payload.prompt.strip()
    if not prompt:
        raise ApiError(400, "A non-empty prompt is required.")
    if len(prompt) > settings.max_prompt_chars:
        raise ApiError(
            400,
            f"That prompt is {len(prompt)} characters; the limit is "
            f"{settings.max_prompt_chars}.",
        )

    # The graph is synchronous (SQLite + the Groq SDK), so keep the event loop free.
    return await run_in_threadpool(run_agent, prompt)


@router.get("/tools")
def tools():
    return {"success": True, "data": list_public_tools()}
