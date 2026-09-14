"""Customer data access.

Every statement is parameterised; no SQL is ever built from caller input. Column
names that reach a query come from module-level allow-lists, never from a caller.

Deletes are soft: `deleted_at` is stamped and every read filters it out. Nothing
here removes a row permanently.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..db import connect
from ..errors import ApiError

TEAMS = ("Design", "AI", "Development", "QA", "Product")
STATUSES = ("active", "on_leave", "alumni")

EDITABLE = ("name", "email", "phone", "team", "title", "location", "status", "joined_at")

# Columns callers may sort by. Anything else is rejected rather than interpolated.
SORTABLE = {
    "id": "id",
    "name": "name COLLATE NOCASE",
    "team": "team COLLATE NOCASE",
    "joined_at": "joined_at",
    "created_at": "created_at",
}

LIVE = "deleted_at IS NULL"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalise_status(value: str | None) -> str | None:
    """Accept the shapes a model or a person actually types.

    The column stores `on_leave`, but "on leave", "on-leave" and "OnLeave" are all
    the same request, and silently returning zero rows for them is worse than useless.
    """
    if not value:
        return None
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "on_leave": "on_leave",
        "onleave": "on_leave",
        "leave": "on_leave",
        "active": "active",
        "current": "active",
        "alumni": "alumni",
        "alumnus": "alumni",
        "former": "alumni",
        "ex": "alumni",
        "left": "alumni",
    }
    resolved = aliases.get(key)
    if resolved is None:
        raise ApiError(400, f'Unknown status "{value}". Use: {", ".join(STATUSES)}.')
    return resolved


def _rows(cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def list_customers(limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    with connect() as conn:
        return _rows(
            conn.execute(
                f"SELECT * FROM customers WHERE {LIVE} ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        )


def count_customers() -> int:
    with connect() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM customers WHERE {LIVE}").fetchone()["n"]


def get_customer(customer_id: int, include_deleted: bool = False) -> dict[str, Any] | None:
    clause = "" if include_deleted else f" AND {LIVE}"
    with connect() as conn:
        row = conn.execute(
            f"SELECT * FROM customers WHERE id = ?{clause}", (customer_id,)
        ).fetchone()
    return dict(row) if row else None


def find_by_name(name: str, limit: int = 25) -> list[dict[str, Any]]:
    """Case-insensitive substring match, escaped so a user-supplied % or _ is literal."""
    with connect() as conn:
        return _rows(
            conn.execute(
                f"SELECT * FROM customers WHERE {LIVE} AND name LIKE ? ESCAPE '\\' "
                "COLLATE NOCASE ORDER BY id DESC LIMIT ?",
                (f"%{_escape_like(name)}%", limit),
            )
        )


def find_exact_by_name(name: str) -> dict[str, Any] | None:
    """Case-insensitive exact match, used to catch accidental re-creation of
    an existing person (a retried prompt, a re-run seed, a second bulk add)."""
    with connect() as conn:
        row = conn.execute(
            f"SELECT * FROM customers WHERE {LIVE} AND name = ? COLLATE NOCASE LIMIT 1",
            (name,),
        ).fetchone()
    return dict(row) if row else None


def get(customer_id: int) -> dict[str, Any] | None:
    """Alias for get_customer, for callers that only ever want a live row."""
    return get_customer(customer_id)


def resolve(name: str) -> dict[str, Any] | None:
    """Best-effort name lookup for callers that degrade gracefully on a miss
    (e.g. an optional meeting host): exact match first, else the single
    case-insensitive substring match, else None. Never raises - resolve_one
    is for the callers that need a hard error on "not found" or "ambiguous".
    """
    exact = find_exact_by_name(name)
    if exact is not None:
        return exact
    matches = find_by_name(name)
    return matches[0] if len(matches) == 1 else None


def search(
    *,
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
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Multi-field search. Every filter is optional; omitting all returns everyone."""
    clauses = [LIVE]
    params: list[Any] = []

    like = {
        "name": name,
        "team": team,
        "title": title,
        "email": email_contains,
        "phone": phone_contains,
        "location": location,
    }
    for column, value in like.items():
        if value:
            clauses.append(f"{column} LIKE ? ESCAPE '\\' COLLATE NOCASE")
            params.append(f"%{_escape_like(value)}%")

    resolved_status = normalise_status(status)
    if resolved_status:
        clauses.append("status = ? COLLATE NOCASE")
        params.append(resolved_status)
    if joined_after:
        clauses.append("joined_at >= ?")
        params.append(joined_after)
    if joined_before:
        clauses.append("joined_at <= ?")
        params.append(joined_before)

    order = SORTABLE.get(sort)
    if order is None:
        raise ApiError(400, f"Cannot sort by \"{sort}\". Try: {', '.join(SORTABLE)}.")

    params.append(limit)
    with connect() as conn:
        return _rows(
            conn.execute(
                f"SELECT * FROM customers WHERE {' AND '.join(clauses)} "
                f"ORDER BY {order} {'DESC' if descending else 'ASC'} LIMIT ?",
                params,
            )
        )


def team_summary() -> list[dict[str, Any]]:
    with connect() as conn:
        return _rows(
            conn.execute(
                f"""SELECT COALESCE(team, 'Unassigned') AS team,
                           COUNT(*) AS headcount,
                           SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active
                    FROM customers WHERE {LIVE}
                    GROUP BY COALESCE(team, 'Unassigned')
                    ORDER BY headcount DESC, team ASC"""
            )
        )


def stats() -> dict[str, Any]:
    with connect() as conn:
        totals = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status = 'active'   THEN 1 ELSE 0 END) AS active,
                       SUM(CASE WHEN status = 'on_leave' THEN 1 ELSE 0 END) AS on_leave,
                       SUM(CASE WHEN status = 'alumni'   THEN 1 ELSE 0 END) AS alumni
                FROM customers WHERE {LIVE}"""
        ).fetchone()
        deleted = conn.execute(
            "SELECT COUNT(*) AS n FROM customers WHERE deleted_at IS NOT NULL"
        ).fetchone()["n"]
        recent = conn.execute(
            f"""SELECT COUNT(*) AS n FROM customers
                WHERE {LIVE} AND joined_at >= date('now', '-90 days')"""
        ).fetchone()["n"]

    return {
        **{k: (totals[k] or 0) for k in ("total", "active", "on_leave", "alumni")},
        "in_recycle_bin": deleted,
        "joined_last_90_days": recent,
        "teams": team_summary(),
    }


def find_deleted_by_name(name: str, limit: int = 25) -> list[dict[str, Any]]:
    """Search the recycle bin. Undo is usually phrased by name, not by ID."""
    with connect() as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM customers WHERE deleted_at IS NOT NULL AND name LIKE ? "
                "ESCAPE '\\' COLLATE NOCASE ORDER BY deleted_at DESC LIMIT ?",
                (f"%{_escape_like(name)}%", limit),
            )
        )


def resolve_deleted(customer_id: int | None, name: str | None) -> dict[str, Any]:
    """Find a deleted customer by ID or name, or raise a caller-safe error."""
    if customer_id is not None:
        found = get_customer(customer_id, include_deleted=True)
        if found is None:
            raise ApiError(404, f"No customer found with ID {customer_id}.")
        if found.get("deleted_at") is None:
            raise ApiError(409, f"{found['name']} is not deleted - nothing to restore.")
        return found

    if name:
        matches = find_deleted_by_name(name)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            options = ", ".join(f"{m['name']} (ID {m['id']})" for m in matches[:5])
            raise ApiError(409, f'Several deleted customers match "{name}": {options}.')
        raise ApiError(404, f'Nothing in the recycle bin matches "{name}".')

    raise ApiError(400, "An ID or a name is required to restore a customer.")


def list_deleted(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM customers WHERE deleted_at IS NOT NULL "
                "ORDER BY deleted_at DESC LIMIT ?",
                (limit,),
            )
        )


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def create_customer(name: str, email: str, phone: str | None = None, **profile) -> dict[str, Any]:
    existing = find_exact_by_name(name)
    if existing is not None:
        raise ApiError(
            409,
            f'A customer named "{name}" already exists (ID {existing["id"]}, '
            f'{existing["email"]}). Use update_customer to change their details instead '
            "of creating a second record.",
        )

    fields = {"name": name, "email": email, "phone": phone or None}
    for key in ("team", "title", "location", "status", "joined_at"):
        if profile.get(key):
            fields[key] = normalise_status(profile[key]) if key == "status" else profile[key]

    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    try:
        with connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO customers ({columns}) VALUES ({placeholders})",
                list(fields.values()),
            )
            new_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper():
            raise ApiError(409, f'A customer with email "{email}" already exists.') from exc
        raise

    created = get_customer(new_id)
    assert created is not None
    return created


def create_many(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Insert several customers, reporting per-record outcomes.

    Deliberately not one transaction: one bad email should not discard the rest.
    """
    created, skipped = [], []
    for index, record in enumerate(records):
        try:
            created.append(create_customer(**record))
        except ApiError as exc:
            skipped.append({"index": index, "name": record.get("name"), "reason": exc.message})
        except TypeError as exc:
            skipped.append({"index": index, "name": record.get("name"), "reason": str(exc)})
    return {"created": created, "skipped": skipped}


def name_parts(full_name: str) -> dict[str, str]:
    """Split a name into the pieces a template can use.

    Slugified for email use: lowercase, accents and punctuation dropped, so
    "Priya  O'Neill-Rao" gives first=priya last=oneillrao.
    """
    import re
    import unicodedata

    def slug(value: str) -> str:
        stripped = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]", "", stripped.lower())

    words = [w for w in re.split(r"\s+", (full_name or "").strip()) if w]
    first = slug(words[0]) if words else ""
    last = slug(words[-1]) if len(words) > 1 else ""
    return {
        "first": first,
        "last": last or first,
        "full": slug(full_name),
        "initials": (first[:1] + (last[:1] if last else "")),
    }


TEMPLATE_FIELDS = ("email", "title", "location")


def render_template(template: str, person: dict[str, Any]) -> str:
    """Fill {first}/{last}/{full}/{initials}/{team} from one person's record.

    Unknown placeholders are left alone rather than raising - a literal value
    containing braces should still pass through untouched.
    """
    values = {
        **name_parts(person.get("name", "")),
        "team": (person.get("team") or "").lower().replace(" ", ""),
        "id": str(person.get("id", "")),
    }
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result


def update_many(
    people: list[dict[str, Any]], fields: dict[str, Any]
) -> dict[str, Any]:
    """Apply the same change to many people, rendering templates per person.

    Deliberately not one transaction: one duplicate email should not discard
    every other update. Each outcome is reported.
    """
    if not people:
        raise ApiError(400, "That matches nobody.")
    if not fields:
        raise ApiError(400, "No changes were provided.")

    updated, skipped = [], []
    for person in people:
        rendered = {
            key: (
                render_template(value, person)
                if key in TEMPLATE_FIELDS and isinstance(value, str)
                else value
            )
            for key, value in fields.items()
        }
        # Nothing to do if every value already matches.
        if all(person.get(key) == value for key, value in rendered.items()):
            skipped.append({"name": person["name"], "reason": "already set"})
            continue
        try:
            updated.append(update_customer(person["id"], rendered))
        except ApiError as exc:
            skipped.append({"name": person["name"], "reason": exc.message})

    return {"updated": [u for u in updated if u], "skipped": skipped}


def update_customer(customer_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    if not fields:
        raise ApiError(400, "No fields were provided to update.")

    unknown = set(fields) - set(EDITABLE)
    if unknown:
        raise ApiError(400, f"Unsupported field(s): {', '.join(sorted(unknown))}")

    if fields.get("status"):
        fields = {**fields, "status": normalise_status(fields["status"])}

    if get_customer(customer_id) is None:
        return None

    # Column names come from EDITABLE above, never from caller input.
    assignments = ", ".join(f"{column} = ?" for column in fields)
    values = list(fields.values()) + [customer_id]

    try:
        with connect() as conn:
            conn.execute(
                f"UPDATE customers SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                values,
            )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper():
            raise ApiError(409, "A customer with this email already exists.") from exc
        raise

    return get_customer(customer_id)


def delete_customer(customer_id: int) -> dict[str, Any] | None:
    """Soft delete. The row stays and can be restored."""
    existing = get_customer(customer_id)
    if existing is None:
        return None
    with connect() as conn:
        conn.execute(
            "UPDATE customers SET deleted_at = datetime('now') WHERE id = ?", (customer_id,)
        )
    return existing


def restore_customer(customer_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE customers SET deleted_at = NULL, updated_at = datetime('now') "
            "WHERE id = ? AND deleted_at IS NOT NULL",
            (customer_id,),
        )
        if cursor.rowcount == 0:
            return None
    return get_customer(customer_id)


def resolve_one(customer_id: int | None, name: str | None, action: str) -> dict[str, Any]:
    """Resolve a customer from an id or a name, or raise a caller-safe error.

    Shared by every tool that acts on one person, so ambiguity behaves identically
    everywhere.
    """
    if customer_id is not None:
        found = get_customer(customer_id)
        if found is None:
            raise ApiError(404, f"No customer found with ID {customer_id}.")
        return found

    if name:
        matches = find_by_name(name)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            options = ", ".join(f"{m['name']} (ID {m['id']})" for m in matches[:5])
            raise ApiError(
                409, f'Multiple customers match "{name}": {options}. Please specify an ID.'
            )
        raise ApiError(404, f'No customer found matching "{name}".')

    raise ApiError(400, f"A customer ID or name is required to {action} a customer.")
