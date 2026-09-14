from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..ratelimit import rate_limit
from ..schemas import MailDraftRequest, MailSendRequest
from ..security import require_admin
from ..services import drafting
from ..services import mail as service

router = APIRouter(prefix="/api/mail", tags=["mail"])


@router.post("/generate", dependencies=[Depends(rate_limit("mail", settings.mail_rate_per_min))])
async def generate(payload: MailDraftRequest):
    draft = await run_in_threadpool(
        drafting.generate_draft,
        recipient=payload.recipient,
        purpose=payload.purpose,
        details=payload.details,
        tone=payload.tone,
    )
    return {"success": True, "data": draft}


@router.post(
    "/send",
    dependencies=[
        Depends(require_admin),
        Depends(rate_limit("mail", settings.mail_rate_per_min)),
    ],
)
async def send(payload: MailSendRequest):
    # The caller's "from" is only ever a Reply-To. The envelope sender is the
    # authenticated SMTP account, so this endpoint cannot be used to spoof anyone.
    await run_in_threadpool(
        service.send_email,
        payload.from_ or "",
        payload.to,
        payload.subject,
        payload.body,
    )

    record = service.record_sent(
        sender=settings.smtp_user,
        recipient=payload.to,
        subject=payload.subject,
        body=payload.body,
    )

    return {"success": True, "message": "Email sent successfully.", "data": record}


@router.get("/sent")
def sent(
    limit: int = Query(default=50, gt=0, le=200),
    offset: int = Query(default=0, ge=0),
):
    return {"success": True, "data": service.list_sent(limit=limit, offset=offset)}
