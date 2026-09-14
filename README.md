# AI Task Agent

Turn a plain-English request into a verified database action.

You type *"add an employee named Aisha Khan with email aisha.khan@example.com"*; a
LangGraph agent picks one tool from a fixed registry, the arguments are re-validated
server-side, the tool runs, and the row appears in the table — with the whole path
shown step by step in the UI.

```
React + Vite  :3000
      │  POST /api/agent/run
      ▼
FastAPI  :8000
      │
      ▼
LangGraph:  classify ──► validate ──► execute ──┐
              (LLM)     (guardrail)   (SQLite)  │
                 ▲           │                  │
                 └───────────┼──────────────────┘  loop, max 5 steps
                             └──► respond   (ask for a detail / decline)
```

The model's only power is **naming** a tool. It never writes SQL, never writes code,
and never decides what a tool does. `validate` re-checks the chosen name against the
local registry and re-validates every argument against that tool's schema before
`execute` touches the database — so a hallucinated tool name or a bad argument is
rejected before anything runs.

**Multi-step.** After each tool runs, its result is fed back and the model decides
what comes next, so one prompt can chain several actions:

> *"Add Iris Chen with email iris.chen@example.com, then email her that orientation
> is Tuesday 9 September at 10am in Room 2B"*
> → `create_customer` → `draft_email` → draft shown for approval

The loop ends when the model replies without calling a tool. A failing step stops the
chain rather than continuing, and `MAX_STEPS` (5) bounds any run.

---

## Quick start

Two terminals.

**Backend**

```bash
cd backend-python
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # then fill it in - see below
python seed.py                  # optional: 11 demo records
python run.py                   # http://127.0.0.1:8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env            # set VITE_ADMIN_TOKEN to match ADMIN_TOKEN
npm run dev                     # http://localhost:3000
```

Requires Python 3.11+ and Node 18+.

---

## Configuration

`backend-python/.env`:

| Variable | Required | Notes |
| --- | --- | --- |
| `GROQ_API_KEY` | for the agent | From [console.groq.com/keys](https://console.groq.com/keys). Without it `/api/agent/run` returns 503. |
| `GROQ_MODEL` | no | Defaults to `openai/gpt-oss-120b`. Must be a **tool-calling** model. |
| `ADMIN_TOKEN` | for writes | Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Without it, every create/update/delete returns 503 — auth fails closed. |
| `FRONTEND_ORIGIN` | no | Comma-separated CORS allow-list. Unset → localhost:3000. Never `*`. |
| `DATABASE_PATH` | no | Defaults to `./database/app.db`. |
| `SMTP_*` | for mail | Host, port, user, pass. Port 587 needs `SMTP_SECURE=false`; port 465 needs `true`. |
| `MAIL_SENDER_NAME` | no | Signs every draft and the From header. Default `Regina Grane`. |
| `MAX_PROMPT_CHARS` | no | Default 2000. Caps what reaches the LLM. |

`frontend/.env` needs `VITE_ADMIN_TOKEN` set to the same value as `ADMIN_TOKEN`.

> The frontend token is bundled into the client build. It is a guard against casual
> and cross-origin access, **not** a user identity. Replace it with real per-user
> auth before exposing this to anyone you don't trust.

---

## Tools

The agent may only ever call tools from this list, one per step, chaining as many as
a request needs. To add a tool, add a spec to `_SPECS` in
[`app/agent/tools.py`](backend-python/app/agent/tools.py) — nothing else needs to change.

| Tool | Method | Endpoint |
| --- | --- | --- |
| `get_customers` | GET | `/api/customers` |
| `get_customer` | GET | `/api/customers/:id` |
| `create_customer` | POST | `/api/customers` |
| `update_customer` | PUT | `/api/customers/:id` |
| `delete_customer` | DELETE | `/api/customers/:id` |
| `draft_email` | POST | `/api/mail/generate` |

Plus two internal control tools the UI doesn't list: `request_clarification` (a
required detail is missing) and `report_unsupported` (nothing here applies). Routing
them through the tool interface means the graph never has to parse free text to work
out what the model meant.

### Email: draft, review, then send

> *"Email Priya Singh to confirm the design review on Thursday at 3pm"*

`draft_email` resolves "Priya Singh" to her address from the records, writes a
subject and body, and hands them back marked `requires_approval`. The draft appears
in the result panel where you can read it, edit either field, and click **Approve &
send** — or discard it.

**The agent cannot send email.** `draft_email` composes and returns; delivery is a
separate call to `POST /api/mail/send`, which requires the admin token. So a prompt
alone — including a maliciously crafted one — can never cause mail to leave the
building. A test asserts no tool in the registry can reach `send_email`.

#### How drafts are written

The writer works in two stages in a single call: it first produces an `analysis`
field reasoning about the situation, then writes the email from it. The analysis is
discarded and never shown — it exists to make the body better than a one-liner.

Output is a structured email: greeting, purpose, two body paragraphs covering cause
and impact, a closing with the concrete next step, and a sign-off. Rich input lands
around 130–160 words; the name it signs off with is `MAIL_SENDER_NAME` (default
**Regina Grane**), which is also the From display name.

> **Honesty outranks length.** Pushing for longer emails initially made the model
> invent facts — an agenda, a prior conversation, and once a fabricated deadline
> ("please confirm by end of day Tuesday") that had never been given. The prompt now
> ranks truth above word count explicitly: thin input produces a *shorter* email
> (~90 words) rather than a padded one. Tests assert those guards stay in place.
>
> This is also why the approval step exists. An LLM writing prose from sparse facts
> will always carry some invention risk — you read the draft before it sends.

**On naming:** `update_customer` takes `match_name` to *find* someone and `new_name`
to *rename* them. Collapsing both into one `name` field is why "rename customer 3 to
Priya" used to fail — the model would fill `name` with the new value and the lookup
would miss.

---

## API

| Route | Auth | Notes |
| --- | --- | --- |
| `GET /api/health` | — | Reports which subsystems are configured |
| `POST /api/agent/run` | — | `{prompt}` → task, steps, result. 20/min |
| `GET /api/agent/tools` | — | Registry, for the Settings panel |
| `GET /api/customers` | — | `?limit=&offset=` |
| `GET /api/customers/{id}` | — | |
| `POST /api/customers` | ✅ | |
| `PUT|PATCH /api/customers/{id}` | ✅ | |
| `DELETE /api/customers/{id}` | ✅ | |
| `GET /api/tasks` | — | Run history, `?limit=&offset=` |
| `GET /api/tasks/{id}` | — | |
| `DELETE /api/tasks/{id}` | ✅ | |
| `GET /api/tasks/activity/recent` | — | Rolling API log |
| `POST /api/mail/generate` | — | Drafts an email. 10/min |
| `POST /api/mail/send` | ✅ | Sends via SMTP. 10/min |
| `GET /api/mail/sent` | — | |

Interactive docs at `http://127.0.0.1:8000/docs`.

Every response is `{"success": bool, ...}`; errors are `{"success": false, "error": "..."}`
and carry a matching HTTP status. Internal detail goes to the server log, never to
the client.

### Mail cannot be used to spoof

`POST /api/mail/send` accepts a `from` address, but it is **only** ever used as
`Reply-To`. The envelope sender is always the authenticated `SMTP_USER`. Combined
with the admin token, this stops the endpoint being an open relay — which is what it
was when `from` went straight to the SMTP transport on an unauthenticated route.

---

## Tests

```bash
cd backend-python
.venv\Scripts\python -m pytest
```

85 tests, ~4 seconds. No network, no API key, no shared database — the model is
stubbed and each test gets its own temporary SQLite file, so the suite runs anywhere.

Coverage worth knowing about:

- the guardrail rejects an unknown tool name and bad arguments **before** execution
- mutating routes are unauthenticated-proof, and auth fails **closed** when unconfigured
- a caller-supplied `from` never becomes the envelope sender
- no tool in the registry can reach `send_email` — drafting cannot become sending
- an ambiguous name (two people called Priya) refuses rather than picking one
- a delivered email that fails to log still returns success, so it isn't sent twice
- a transient empty generation from Groq is retried, not surfaced as a failure
- a multi-step chain records every call, and a failing step halts the rest
- `MAX_STEPS` bounds a runaway loop
- the drafting prompt keeps its honesty-over-length guards

---

## Layout

```
backend-python/
  app/
    main.py          FastAPI app, CORS, body limits, activity middleware
    config.py        env loading and validation
    db.py            SQLite connections, schema, migrations
    security.py      admin token (fail-closed)
    schemas.py       request models
    agent/
      graph.py       the LangGraph StateGraph
      tools.py       tool registry + argument schemas
      llm.py         lazy Groq client
      service.py     graph run -> task history record
    routers/         HTTP layer
    services/        data access
  tests/
frontend/
  src/
    pages/Dashboard.jsx
    components/
    services/api.js
backend/             superseded Node backend - safe to delete
```

---

## Notes

- **`backend/` is the old Node backend.** It has been fully replaced and is no longer
  wired to anything. Delete it once you're satisfied with this one.
- The database file is unchanged in shape, so an existing `app.db` still works; copy
  it to `backend-python/database/` to keep your data. One additive migration runs
  automatically (an `api_activity.source` column).
- Activity logging is real middleware now. The Node version only logged calls the
  agent made, so the panel never showed the requests the UI itself was making.
