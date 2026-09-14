"""LLM email drafting.

Shared by POST /api/mail/generate and the agent's `draft_email` tool, so both
produce identical drafts from identical inputs.

Nothing here sends anything. Drafting and sending are deliberately separate steps:
the agent can compose a message, but only an authenticated human hitting
POST /api/mail/send can actually deliver it.
"""

from __future__ import annotations

import json
import logging

from ..agent.llm import get_llm
from ..config import settings
from ..errors import ApiError

log = logging.getLogger("app.drafting")

SYSTEM_PROMPT = """You are an experienced business correspondent writing on behalf of
{sender}.

Work in two stages.

STAGE 1 - ANALYSE. Before writing a word of the email, think through:
  - What situation is actually being communicated, and why does it matter to this
    recipient?
  - What does the recipient need to understand, and what do they need to DO?
  - What consequences, context, or next steps follow from the facts given?
  - What tone and level of formality fit this relationship?

STAGE 2 - WRITE. Turn that analysis into a complete, well-structured email.

STRUCTURE (follow it):
  1. A greeting addressing the recipient by name.
  2. An opening line stating the purpose of the email directly.
  3. TWO body paragraphs - this is the heart of the email and the part that must not
     be thin:
       - the first explains the situation and WHY it came about;
       - the second explains what it MEANS for the recipient - the impact on them,
         what is being done about it, and what changes as a result.
     Both must be built ONLY from the facts you were given. Never open a sentence
     with "further to our discussion", "as we discussed", "following up on", or any
     other reference to a previous conversation, meeting, email, or attachment
     unless KEY DETAILS explicitly mentions one.
  4. A clear closing paragraph stating the specific action or next step, when it is
     needed by, what happens once it is done, and an offer to discuss further.
  5. A sign-off followed by the name {sender} on its own line.

LENGTH: aim for 150-230 words across 4 or 5 paragraphs. A one or two line email is a
failure, and so is a single thin body paragraph. Reach the length by explaining
cause, impact and next steps properly - never by padding with filler courtesies or
restating the same point twice. Separate every paragraph with a blank line.

HONESTY OUTRANKS LENGTH. This is the rule that wins when the two conflict.

Use every relevant fact from KEY DETAILS. Never state anything that was not given to
you. In particular, never invent:
  - a date, time, or deadline ("please confirm by Tuesday" when no deadline exists)
  - a reason, cause, or agenda for something
  - a name, figure, price, or quantity
  - an attendee, location detail, attachment, or prior conversation
  - a consequence or commitment on anyone's behalf

When KEY DETAILS are thin, WRITE A SHORTER EMAIL. Missing the word count is not a
failure; inventing one fact to reach it is. Eighty honest words beat two hundred
containing a single fabrication - the user may send this message as-is, and an
invented deadline becomes a real promise made in their name.

Legitimate elaboration is explaining the significance of what you WERE told, and
using ordinary open phrasing ("please let me know if that time still works") that
commits to no new fact. That is how you add substance without inventing.

Write in a {tone} tone. Sign off as {sender} and no one else.

Return ONLY a JSON object of exactly this shape, with no markdown fences:
{{"analysis": "string", "subject": "string", "body": "string"}}

`analysis` is your stage 1 thinking in two or three sentences; it is discarded and
never shown to anyone. `subject` is specific and informative, not generic. `body` is
the finished email including greeting and sign-off, with \\n between paragraphs."""


def _strip_fences(raw: str) -> str:
    """Models occasionally wrap JSON in ```json fences despite instructions."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    text = text.strip("`").strip()
    if text.lower().startswith("json"):
        text = text[4:].strip()
    return text


def generate_draft(
    *,
    recipient: str,
    purpose: str,
    details: str = "",
    tone: str = "professional",
) -> dict[str, str]:
    """Return {"subject", "body"}. Raises ApiError on anything unusable."""
    llm = get_llm(temperature=0.35)

    reply = llm.invoke(
        [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    tone=tone or "professional", sender=settings.mail_sender_name
                ),
            },
            {
                "role": "user",
                "content": (
                    f"RECIPIENT:\n{recipient}\n\n"
                    f"PURPOSE:\n{purpose}\n\n"
                    f"KEY DETAILS (follow and incorporate these):\n---\n"
                    f"{(details or '').strip() or 'None provided'}\n---"
                ),
            },
        ]
    )

    content = reply.content if isinstance(reply.content, str) else ""

    try:
        parsed = json.loads(_strip_fences(content))
    except (ValueError, TypeError) as exc:
        log.warning("Draft was not valid JSON: %s", content[:200])
        raise ApiError(502, "The AI returned a malformed email draft. Try again.") from exc

    if not isinstance(parsed, dict):
        raise ApiError(502, "The AI returned a malformed email draft. Try again.")

    subject = str(parsed.get("subject") or "").strip()
    body = str(parsed.get("body") or "").strip()
    if not subject or not body:
        raise ApiError(502, "The AI returned an incomplete email draft. Try again.")

    # `analysis` is stage-1 reasoning. It exists to make the body better, and is
    # deliberately dropped rather than shown.
    log.debug("draft analysis: %s", str(parsed.get("analysis", ""))[:300])

    return {"subject": subject, "body": _ensure_signoff(body)}


def _ensure_signoff(body: str) -> str:
    """Guarantee the configured name closes the email, even if the model forgot."""
    sender = settings.mail_sender_name
    if sender.lower() in body[-200:].lower():
        return body
    return f"{body.rstrip()}\n\nBest regards,\n{sender}"
