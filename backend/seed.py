"""Populate the database with a realistic demo team:  python seed.py

30 people across Design, AI, Development, QA and Product, with titles, locations,
join dates and a few notes - enough for the agent's search, team and stats tools to
return something meaningful.

Re-running is safe: rows are matched on email or name and left alone if already
present - matching on email alone would let a renamed record (e.g. from a bulk
email update) slip past the check and get reseeded as a duplicate person.
"""

from __future__ import annotations

from app.db import connect, init_database
from app.services.leave import _working_days

# name, email, phone, team, title, location, status, joined_at
PEOPLE = [
    # --- Design -------------------------------------------------------------
    ("Priya Singh", "priya.singh@example.com", "9876511111", "Design", "Design Lead", "Bengaluru", "active", "2021-03-15"),
    ("Meera Nair", "meera.nair@example.com", "9876566666", "Design", "Senior Product Designer", "Kochi", "active", "2021-11-02"),
    ("Aditya Rao", "aditya.rao@example.com", "9811100011", "Design", "UX Researcher", "Pune", "active", "2023-01-09"),
    ("Sana Qureshi", "sana.qureshi@example.com", "9811100012", "Design", "Product Designer", "Bengaluru", "active", "2023-07-24"),
    ("Tanvi Bhatt", "tanvi.bhatt@example.com", "9811100013", "Design", "Visual Designer", "Ahmedabad", "active", "2024-02-12"),
    ("Rohit Menon", "rohit.menon@example.com", "9811100014", "Design", "Design Systems Engineer", "Chennai", "on_leave", "2022-06-20"),
    ("Ishita Ghosh", "ishita.ghosh@example.com", "9811100015", "Design", "Motion Designer", "Kolkata", "active", "2024-09-02"),

    # --- AI -----------------------------------------------------------------
    ("Rahul Sharma", "rahul.sharma@example.com", "9876543210", "AI", "Head of AI", "Bengaluru", "active", "2020-08-03"),
    ("Aisha Khan", "aisha.khan@example.com", "9876544444", "AI", "Senior ML Engineer", "Hyderabad", "active", "2021-09-13"),
    ("Vikram Joshi", "vikram.joshi@example.com", "9876555555", "AI", "ML Engineer", "Pune", "active", "2022-04-11"),
    ("Nikhil Reddy", "nikhil.reddy@example.com", "9811100021", "AI", "Research Scientist", "Hyderabad", "active", "2022-10-17"),
    ("Fatima Sheikh", "fatima.sheikh@example.com", "9811100022", "AI", "NLP Engineer", "Mumbai", "active", "2023-03-06"),
    ("Arjun Kapoor", "arjun.kapoor@example.com", "9876577777", "AI", "MLOps Engineer", "Bengaluru", "active", "2023-08-21"),
    ("Divya Pillai", "divya.pillai@example.com", "9811100023", "AI", "Data Scientist", "Kochi", "active", "2024-01-15"),
    ("Karthik Iyer", "karthik.iyer@example.com", "9811100024", "AI", "Applied Scientist", "Chennai", "active", "2024-11-04"),

    # --- Development --------------------------------------------------------
    ("Aman Verma", "aman.verma@example.com", "9876500000", "Development", "Engineering Manager", "Bengaluru", "active", "2020-02-10"),
    ("Neha Gupta", "neha.gupta@example.com", "9876522222", "Development", "Staff Engineer", "Noida", "active", "2020-11-23"),
    ("Karan Mehta", "karan.mehta@example.com", "9876533333", "Development", "Senior Backend Engineer", "Mumbai", "active", "2021-05-04"),
    ("Simran Das", "simran.das@example.com", "9876588888", "Development", "Senior Frontend Engineer", "Kolkata", "active", "2021-08-30"),
    ("Dev Malhotra", "dev.malhotra@example.com", "9876599999", "Development", "Backend Engineer", "Delhi", "active", "2022-01-17"),
    ("Ananya Iyer", "ananya.iyer@example.com", "9811100031", "Development", "Full Stack Engineer", "Bengaluru", "active", "2022-09-05"),
    ("Zoya Ansari", "zoya.ansari@example.com", "9811100032", "Development", "Frontend Engineer", "Hyderabad", "active", "2023-04-18"),
    ("Harsh Patel", "harsh.patel@example.com", "9811100033", "Development", "Platform Engineer", "Ahmedabad", "active", "2023-11-27"),
    ("Manav Bose", "manav.bose@example.com", "9811100034", "Development", "Site Reliability Engineer", "Pune", "active", "2024-05-13"),
    ("Ritu Chauhan", "ritu.chauhan@example.com", "9811100035", "Development", "Mobile Engineer", "Jaipur", "alumni", "2021-02-08"),

    # --- QA -----------------------------------------------------------------
    ("Sneha Kulkarni", "sneha.kulkarni@example.com", "9811100041", "QA", "QA Lead", "Pune", "active", "2021-07-19"),
    ("Imran Sayed", "imran.sayed@example.com", "9811100042", "QA", "Automation Engineer", "Mumbai", "active", "2023-02-27"),
    ("Pooja Nambiar", "pooja.nambiar@example.com", "9811100043", "QA", "QA Engineer", "Kochi", "active", "2024-06-10"),

    # --- Product ------------------------------------------------------------
    ("Kabir Chandra", "kabir.chandra@example.com", "9811100051", "Product", "Head of Product", "Bengaluru", "active", "2020-06-01"),
    ("Lakshmi Menon", "lakshmi.menon@example.com", "9811100052", "Product", "Product Manager", "Chennai", "active", "2022-03-14"),
    ("Yash Trivedi", "yash.trivedi@example.com", "9811100053", "Product", "Technical Program Manager", "Delhi", "on_leave", "2023-09-25"),
]

# email, type, start, end, reason, status
# Weighted towards pending so there is something to approve on day one.
LEAVE = [
    ("rohit.menon@example.com", "parental", "2026-08-10", "2026-10-09", "Parental leave", "approved"),
    ("yash.trivedi@example.com", "sick", "2026-08-24", "2026-09-04", "Surgery recovery", "approved"),
    ("priya.singh@example.com", "annual", "2026-09-14", "2026-09-18", "Family wedding", "pending"),
    ("aisha.khan@example.com", "annual", "2026-09-21", "2026-09-25", "Trip to Goa", "pending"),
    ("karan.mehta@example.com", "sick", "2026-08-31", "2026-09-01", "Dental surgery", "pending"),
    ("meera.nair@example.com", "casual", "2026-09-07", "2026-09-07", "House move", "pending"),
    ("harsh.patel@example.com", "annual", "2026-10-05", "2026-10-16", "Diwali with family", "pending"),
    ("sneha.kulkarni@example.com", "annual", "2026-09-28", "2026-09-30", "Short break", "pending"),
    ("nikhil.reddy@example.com", "unpaid", "2026-11-02", "2026-11-27", "Sabbatical", "pending"),
    ("zoya.ansari@example.com", "casual", "2026-09-11", "2026-09-11", "Personal errand", "pending"),
    ("simran.das@example.com", "annual", "2026-07-06", "2026-07-10", "Summer holiday", "approved"),
    ("dev.malhotra@example.com", "annual", "2026-12-21", "2026-12-31", "Year end", "pending"),
    ("aman.verma@example.com", "casual", "2026-08-03", "2026-08-03", "Personal", "rejected"),
]


# email -> note, so the profile view has something to show on day one.
NOTES = {
    "priya.singh@example.com": "Owns the design system rewrite. Prefers async reviews over meetings.",
    "rahul.sharma@example.com": "Sign-off needed on any model change that touches production inference.",
    "aman.verma@example.com": "Main escalation point for backend incidents.",
    "aisha.khan@example.com": "Leading the retrieval quality workstream.",
    "rohit.menon@example.com": "On parental leave, back in October.",
    "ritu.chauhan@example.com": "Left in 2024, still a referral source for mobile candidates.",
    "sneha.kulkarni@example.com": "Runs the release checklist; loop in before any deploy.",
    "kabir.chandra@example.com": "Sets quarterly roadmap. Best reached mornings.",
}


def main() -> None:
    init_database()

    with connect() as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"]

        for name, email, phone, team, title, location, status, joined_at in PEOPLE:
            already = conn.execute(
                "SELECT 1 FROM customers WHERE email = ? OR name = ? COLLATE NOCASE",
                (email, name),
            ).fetchone()
            if already:
                continue
            conn.execute(
                """INSERT INTO customers
                   (name, email, phone, team, title, location, status, joined_at, is_seed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (name, email, phone, team, title, location, status, joined_at),
            )

        for email, kind, start, end, reason, status in LEAVE:
            row = conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
            if not row:
                continue
            already = conn.execute(
                "SELECT 1 FROM leave_requests WHERE customer_id = ? AND start_date = ?",
                (row["id"], start),
            ).fetchone()
            if already:
                continue
            days = _working_days(start, end)
            decided = "'seed'" if status != "pending" else "NULL"
            conn.execute(
                f"""INSERT INTO leave_requests
                    (customer_id, leave_type, start_date, end_date, days, reason, status,
                     decided_by, decided_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, {decided},
                            CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END)""",
                (row["id"], kind, start, end, days, reason, status, status),
            )

        for email, body in NOTES.items():
            row = conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
            if not row:
                continue
            already = conn.execute(
                "SELECT 1 FROM notes WHERE customer_id = ? AND body = ?", (row["id"], body)
            ).fetchone()
            if not already:
                conn.execute(
                    "INSERT INTO notes (customer_id, body, author) VALUES (?, ?, 'seed')",
                    (row["id"], body),
                )

        total = conn.execute(
            "SELECT COUNT(*) AS n FROM customers WHERE deleted_at IS NULL"
        ).fetchone()["n"]
        notes = conn.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"]
        leave = conn.execute(
            "SELECT status, COUNT(*) AS n FROM leave_requests GROUP BY status"
        ).fetchall()
        teams = conn.execute(
            """SELECT team, COUNT(*) AS n FROM customers
               WHERE deleted_at IS NULL GROUP BY team ORDER BY n DESC"""
        ).fetchall()

    print(f"Seed complete. {total} people ({total - before} new), {notes} notes.")
    for row in teams:
        print(f"  {row['team'] or 'Unassigned':<12} {row['n']}")
    print("Leave requests:")
    for row in leave:
        print(f"  {row['status']:<12} {row['n']}")




def seed_attendance(days_back: int = 14) -> None:
    """Fill recent working days with plausible attendance.

    Deterministic - a fixed pattern per person, so the grid looks realistic and a
    re-run does not churn the data.
    """
    from datetime import date, timedelta

    from app.services.attendance import mark, working_days

    today = date.today()
    start = (today - timedelta(days=days_back)).isoformat()
    days = working_days(start, today.isoformat())

    with connect() as conn:
        people = conn.execute(
            "SELECT id, name FROM customers WHERE deleted_at IS NULL AND status != 'alumni' "
            "ORDER BY id"
        ).fetchall()
        already = conn.execute("SELECT COUNT(*) AS n FROM attendance").fetchone()["n"]

    if already:
        print(f"Attendance already seeded ({already} records) - skipping.")
        return

    written = 0
    for index, person in enumerate(people):
        for offset, day in enumerate(days):
            # A repeatable pattern: mostly present, occasional remote or absence.
            slot = (index * 7 + offset * 3) % 20
            if slot == 4:
                status = "absent"
            elif slot in (1, 11):
                status = "wfh"
            elif slot == 17:
                status = "half_day"
            else:
                status = "present"
            mark(person["id"], status, day, marked_by="seed")
            written += 1
    print(f"Attendance seeded: {written} records across {len(days)} working days.")




# Team leads become the manager for everyone else on their team.
MANAGERS = {
    "Design": "priya.singh@example.com",
    "AI": "rahul.sharma@example.com",
    "Development": "aman.verma@example.com",
    "QA": "sneha.kulkarni@example.com",
    "Product": "kabir.chandra@example.com",
}

# title, assignee email (or None), team, priority, status, due offset in days
WORK = [
    ("Ship the design system v2 tokens", "priya.singh@example.com", "Design", "high", "in_progress", 12),
    ("Audit colour contrast across the app", "sana.qureshi@example.com", "Design", "medium", "todo", 20),
    ("Motion spec for the onboarding flow", "ishita.ghosh@example.com", "Design", "low", "todo", 35),
    ("Retrieval quality eval harness", "aisha.khan@example.com", "AI", "urgent", "in_progress", 5),
    ("Cut inference cost by 30%", "rahul.sharma@example.com", "AI", "high", "todo", 40),
    ("Label the Q3 intent dataset", "divya.pillai@example.com", "AI", "medium", "blocked", -3),
    ("Model card for the ranking model", "nikhil.reddy@example.com", "AI", "low", "todo", 55),
    ("Migrate auth service to the new gateway", "karan.mehta@example.com", "Development", "urgent", "in_progress", 2),
    ("Fix flaky checkout integration tests", "zoya.ansari@example.com", "Development", "high", "todo", -1),
    ("Upgrade Postgres to 16", "harsh.patel@example.com", "Development", "medium", "todo", 25),
    ("Add request tracing to the API", "manav.bose@example.com", "Development", "medium", "done", -10),
    ("Frontend bundle size budget", "simran.das@example.com", "Development", "low", "todo", 45),
    ("Release checklist automation", "sneha.kulkarni@example.com", "QA", "high", "in_progress", 8),
    ("Regression suite for billing", "imran.sayed@example.com", "QA", "medium", "todo", 18),
    ("Q4 roadmap draft", "kabir.chandra@example.com", "Product", "high", "in_progress", 15),
    ("Customer interview synthesis", "lakshmi.menon@example.com", "Product", "medium", "done", -6),
    ("Pricing experiment brief", None, "Product", "medium", "todo", 30),
    ("Accessibility statement for the site", None, "Design", "low", "todo", 60),
]


def seed_work() -> None:
    """Managers plus a realistic backlog, including a few overdue items."""
    from datetime import date, timedelta

    with connect() as conn:
        if conn.execute("SELECT COUNT(*) AS n FROM work_tasks").fetchone()["n"]:
            print("Work tasks already seeded - skipping.")
            return

        ids = {
            row["email"]: row["id"]
            for row in conn.execute("SELECT id, email FROM customers").fetchall()
        }

        linked = 0
        for team, lead_email in MANAGERS.items():
            lead = ids.get(lead_email)
            if not lead:
                continue
            linked += conn.execute(
                "UPDATE customers SET manager_id = ? WHERE team = ? AND id != ?",
                (lead, team, lead),
            ).rowcount

        today = date.today()
        for title, email, team, priority, status, offset in WORK:
            conn.execute(
                """INSERT INTO work_tasks
                   (title, priority, status, assignee_id, team, due_date, created_by,
                    completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'seed', ?)""",
                (
                    title,
                    priority,
                    status,
                    ids.get(email) if email else None,
                    team,
                    (today + timedelta(days=offset)).isoformat(),
                    (today - timedelta(days=2)).isoformat() if status == "done" else None,
                ),
            )

# title, host_email, team, day_offset, start_hour, duration_minutes, location, attendee_emails
MEETINGS_SAMPLE = [
    ("Sprint Planning & Backlog Triage", "aman.verma@example.com", "Development", 0, 10, 60, "Room Beta / Meet", ["karan.mehta@example.com", "simran.das@example.com", "dev.malhotra@example.com", "zoya.ansari@example.com"]),
    ("AI Retrieval Quality Evaluation", "rahul.sharma@example.com", "AI", 0, 14, 45, "AI Lab / Meet", ["aisha.khan@example.com", "vikram.joshi@example.com", "nikhil.reddy@example.com"]),
    ("Design System Token Sync", "priya.singh@example.com", "Design", 0, 16, 30, "Design Studio", ["meera.nair@example.com", "sana.qureshi@example.com", "tanvi.bhatt@example.com"]),
    ("QA Automation & Regression Review", "sneha.kulkarni@example.com", "QA", 1, 11, 45, "Meet", ["imran.sayed@example.com", "pooja.nambiar@example.com"]),
    ("Q4 Product Strategy & Roadmapping", "kabir.chandra@example.com", "Product", 1, 15, 60, "Executive Room / Meet", ["lakshmi.menon@example.com", "rahul.sharma@example.com", "aman.verma@example.com", "priya.singh@example.com"]),
    ("Backend Performance & Tracing Sync", "aman.verma@example.com", "Development", 2, 10, 30, "Meet", ["manav.bose@example.com", "harsh.patel@example.com", "karan.mehta@example.com"]),
    ("1-on-1: Career Growth & Feedback", "rahul.sharma@example.com", "AI", 2, 13, 30, "Meet", ["aisha.khan@example.com"]),
    ("Frontend Bundle Budget Review", "simran.das@example.com", "Development", 3, 11, 30, "Meet", ["ananya.iyer@example.com", "zoya.ansari@example.com"]),
    ("All-Hands Monthly Engineering Sync", "aman.verma@example.com", "General", 4, 16, 60, "Townhall / Zoom", ["rahul.sharma@example.com", "priya.singh@example.com", "sneha.kulkarni@example.com", "kabir.chandra@example.com"]),
    ("NLP Prompt Evaluation Workshop", "fatima.sheikh@example.com", "AI", 5, 14, 45, "AI Hub", ["arjun.kapoor@example.com", "divya.pillai@example.com", "karthik.iyer@example.com"]),
]


def seed_meetings() -> None:
    """Populate demo calendar meetings across teams."""
    import json
    from datetime import date, datetime, time, timedelta

    with connect() as conn:
        if conn.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"]:
            print("Meetings already seeded - skipping.")
            return

        people_map = {
            row["email"]: {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "team": row["team"],
            }
            for row in conn.execute("SELECT id, name, email, team FROM customers").fetchall()
        }

        today = date.today()
        count = 0

        for title, host_email, team, day_offset, start_hour, duration_min, loc, att_emails in MEETINGS_SAMPLE:
            host_person = people_map.get(host_email)
            target_date = today + timedelta(days=day_offset)
            start_dt = datetime.combine(target_date, time(hour=start_hour, minute=0))
            end_dt = start_dt + timedelta(minutes=duration_min)

            attendee_objs = [people_map[e] for e in att_emails if e in people_map]

            conn.execute(
                """INSERT INTO meetings
                   (title, description, team, start_time, end_time, location_or_link, host_id, attendees, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')""",
                (
                    title,
                    f"Team sync for {team} on upcoming sprint deliverables and blockers.",
                    team,
                    start_dt.isoformat(),
                    end_dt.isoformat(),
                    loc,
                    host_person["id"] if host_person else None,
                    json.dumps(attendee_objs),
                ),
            )
            count += 1

    print(f"Meetings seeded: {count} events across teams.")


if __name__ == "__main__":
    main()
    seed_attendance()
    seed_work()
    seed_meetings()
