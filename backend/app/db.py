"""SQLite access: connection handling, schema creation, and lightweight migration.

Every query in this app goes through `connect()`. Nothing else opens the file, and
no SQL is ever built by string concatenation with caller data.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings

_db_path: Path = settings.database_path


def set_database_path(path: Path | str) -> None:
    """Point the app at a different database file. Used by the test suite."""
    global _db_path
    _db_path = Path(path)


def get_database_path() -> Path:
    return _db_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close.

    SQLite connections are cheap, and WAL lets readers run alongside a writer, so
    one connection per unit of work is both simpler and safer than a shared handle
    across FastAPI's thread pool.
    """
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL lets reads proceed during a write. The Node version used DELETE,
        # which serialises every reader against every writer.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    phone      TEXT,
    team       TEXT,
    title      TEXT,
    location   TEXT,
    status     TEXT NOT NULL DEFAULT 'active',
    joined_at  TEXT,
    manager_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    is_seed    INTEGER NOT NULL DEFAULT 0,
    -- Soft delete. Every read filters on this being NULL, so a delete is
    -- reversible: an agent that can chain five steps unattended must not be able
    -- to destroy a record outright.
    deleted_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    leave_type    TEXT NOT NULL DEFAULT 'annual',
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    days          INTEGER NOT NULL DEFAULT 1,
    reason        TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    decided_by    TEXT,
    decision_note TEXT,
    requested_at  TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at    TEXT
);

-- Work assigned to people. Distinct from the `tasks` table above, which is the
-- agent's own run history - two different meanings of the word.
CREATE TABLE IF NOT EXISTS work_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT,
    priority     TEXT NOT NULL DEFAULT 'medium',
    status       TEXT NOT NULL DEFAULT 'todo',
    assignee_id  INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    team         TEXT,
    due_date     TEXT,
    created_by   TEXT NOT NULL DEFAULT 'agent',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    day         TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'present',
    note        TEXT,
    marked_by   TEXT NOT NULL DEFAULT 'agent',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    -- One record per person per day. Marking the same day again updates it
    -- rather than stacking duplicates.
    UNIQUE (customer_id, day)
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    body        TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT 'agent',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt       TEXT NOT NULL,
    intent       TEXT,
    tool_name    TEXT,
    parameters   TEXT,
    method       TEXT,
    endpoint     TEXT,
    status       TEXT NOT NULL DEFAULT 'pending',
    result       TEXT,
    error        TEXT,
    duration_ms  INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS api_activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    method      TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    source      TEXT NOT NULL DEFAULT 'http',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sent_emails (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    sender    TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject   TEXT NOT NULL,
    body      TEXT NOT NULL,
    sent_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meetings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    title            TEXT NOT NULL,
    description      TEXT,
    team             TEXT,
    start_time       TEXT NOT NULL,
    end_time         TEXT NOT NULL,
    location_or_link TEXT,
    host_id          INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    attendees        TEXT NOT NULL DEFAULT '[]',
    status           TEXT NOT NULL DEFAULT 'scheduled',
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Case-insensitive lookups by name are the agent's hottest path.
CREATE INDEX IF NOT EXISTS idx_customers_name_nocase ON customers(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_customers_email       ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_team        ON customers(team COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_customers_live        ON customers(deleted_at);
CREATE INDEX IF NOT EXISTS idx_notes_customer        ON notes(customer_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_leave_status          ON leave_requests(status, start_date);
CREATE INDEX IF NOT EXISTS idx_leave_customer        ON leave_requests(customer_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_day        ON attendance(day DESC, status);
CREATE INDEX IF NOT EXISTS idx_attendance_customer   ON attendance(customer_id, day DESC);
CREATE INDEX IF NOT EXISTS idx_work_assignee         ON work_tasks(assignee_id, status);
CREATE INDEX IF NOT EXISTS idx_work_status           ON work_tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_customers_manager     ON customers(manager_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created         ON tasks(id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_created      ON api_activity(id DESC);
CREATE INDEX IF NOT EXISTS idx_sent_emails_sent      ON sent_emails(id DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_start        ON meetings(start_time);
CREATE INDEX IF NOT EXISTS idx_meetings_team         ON meetings(team COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_meetings_status       ON meetings(status);
"""


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_database() -> None:
    """Create tables and indexes, and apply additive migrations to existing files."""
    with connect() as conn:
        conn.executescript(SCHEMA)

        # Migration: databases created by the previous Node backend predate `source`.
        if "source" not in _column_names(conn, "api_activity"):
            conn.execute(
                "ALTER TABLE api_activity ADD COLUMN source TEXT NOT NULL DEFAULT 'http'"
            )

        # Migration: profile fields and soft delete, added after the first release.
        # Additive and idempotent, so an existing app.db keeps its rows.
        existing = _column_names(conn, "customers")
        for column, ddl in (
            ("team", "TEXT"),
            ("title", "TEXT"),
            ("location", "TEXT"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("joined_at", "TEXT"),
            ("deleted_at", "TEXT"),
            ("manager_id", "INTEGER REFERENCES customers(id)"),
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE customers ADD COLUMN {column} {ddl}")
