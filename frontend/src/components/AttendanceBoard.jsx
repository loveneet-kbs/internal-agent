import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarCheck, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { Avatar, TeamBadge, TEAMS } from "./TeamBadge.jsx";
import LoadingState from "./LoadingState.jsx";
import { errorMessage, getAttendance, markAttendance } from "../services/api.js";

// The cycle a cell steps through when clicked, and how each renders.
const CYCLE = ["present", "absent", "leave", "half_day", "wfh"];

const CELL = {
  present: { short: "P", className: "text-success border-success/40 bg-success/12" },
  absent: { short: "A", className: "text-danger border-danger/40 bg-danger/12" },
  leave: { short: "L", className: "text-warning border-warning/40 bg-warning/12" },
  half_day: { short: "H", className: "text-info border-info/40 bg-info/12" },
  wfh: { short: "R", className: "text-accent border-accent/40 bg-accent/12" },
  unmarked: { short: "·", className: "text-muted border-line/25 bg-glass/15" }
};

const FULL = {
  present: "Present",
  absent: "Absent",
  leave: "Leave",
  half_day: "Half day",
  wfh: "Remote",
  unmarked: "Not marked"
};

// `date.toISOString()` converts to UTC first, which silently shifts the
// calendar day by one in most timezones (e.g. during the first ~5.5 hours
// of the day in India, UTC+5:30). Build/read the "YYYY-MM-DD" from local
// date parts instead, everywhere in this file, so "today" and its label
// always agree with the viewer's actual wall-clock day.
function isoDay(offsetFromToday) {
  const d = new Date();
  d.setDate(d.getDate() + offsetFromToday);
  return toLocalIso(d);
}

function toLocalIso(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** The last `count` weekdays ending at `endOffset` days from today, oldest first. */
function weekdayRange(count, endOffset) {
  const days = [];
  let offset = endOffset;
  while (days.length < count) {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    if (d.getDay() !== 0 && d.getDay() !== 6) days.push(toLocalIso(d));
    offset -= 1;
  }
  return days.reverse();
}

function dayLabel(iso) {
  const [y, m, day] = iso.split("-").map(Number);
  const d = new Date(y, m - 1, day);
  return {
    weekday: d.toLocaleDateString(undefined, { weekday: "short" }),
    date: d.toLocaleDateString(undefined, { day: "2-digit", month: "short" })
  };
}

const COLUMNS = 7;

export default function AttendanceBoard({ customers = [], onOpenProfile }) {
  const [endOffset, setEndOffset] = useState(0);
  const [team, setTeam] = useState("All");
  const [records, setRecords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");

  const days = useMemo(() => weekdayRange(COLUMNS, endOffset), [endOffset]);
  const today = isoDay(0);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const { data } = await getAttendance({ since: days[0], until: days.at(-1), limit: 500 });
      setRecords(data.data);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load attendance."));
    } finally {
      setIsLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  // (customer_id, day) -> status, for O(1) cell lookup.
  const grid = useMemo(() => {
    const map = new Map();
    for (const record of records) map.set(`${record.customer_id}|${record.day}`, record.status);
    return map;
  }, [records]);

  const people = useMemo(
    () =>
      customers
        .filter((p) => p.status !== "alumni")
        .filter((p) => team === "All" || p.team === team)
        .sort((a, b) => a.name.localeCompare(b.name)),
    [customers, team]
  );

  const cycle = async (person, day) => {
    const current = grid.get(`${person.id}|${day}`) ?? "unmarked";
    const index = CYCLE.indexOf(current);
    const next = CYCLE[(index + 1) % CYCLE.length];

    const key = `${person.id}|${day}`;
    setSaving(key);
    setError("");
    // Optimistic: the grid should feel instant, and a failure re-syncs below.
    setRecords((previous) => [
      ...previous.filter((r) => !(r.customer_id === person.id && r.day === day)),
      { customer_id: person.id, day, status: next, id: `temp-${key}` }
    ]);
    try {
      await markAttendance({ customer_id: person.id, status: next, day });
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not save that mark."));
      await load();
    } finally {
      setSaving("");
    }
  };

  const totals = useMemo(() => {
    const tally = { present: 0, absent: 0, leave: 0, half_day: 0, wfh: 0 };
    for (const person of people) {
      const status = grid.get(`${person.id}|${today}`);
      if (status && status in tally) tally[status] += 1;
    }
    return tally;
  }, [people, grid, today]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">
            Daily record
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-text">Attendance</h2>
          <p className="mt-1 text-sm text-muted">
            Today: {totals.present} present · {totals.absent} absent · {totals.leave} on leave ·{" "}
            {totals.wfh} remote
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setEndOffset((o) => o - COLUMNS)}
            aria-label="Earlier days"
            className="glass glass-hover rounded-full p-2 text-text-2 hover:text-accent"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            type="button"
            disabled={endOffset >= 0}
            onClick={() => setEndOffset((o) => Math.min(0, o + COLUMNS))}
            aria-label="Later days"
            className="glass glass-hover rounded-full p-2 text-text-2 hover:text-accent disabled:opacity-40"
          >
            <ChevronRight size={14} />
          </button>
          <button
            type="button"
            onClick={load}
            className="glass glass-hover flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-text-2 hover:text-accent"
          >
            <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      <div className="glass rounded-2xl p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1.5">
            {["All", ...TEAMS].map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => setTeam(name)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                  team === name
                    ? "border-accent/45 bg-accent/12 text-accent"
                    : "border-line/30 text-muted hover:text-text-2"
                }`}
              >
                {name}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] text-muted">
            {CYCLE.map((status) => (
              <span key={status} className="flex items-center gap-1">
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded border text-[9px] font-semibold ${CELL[status].className}`}
                >
                  {CELL[status].short}
                </span>
                {FULL[status]}
              </span>
            ))}
          </div>
        </div>

        {error && (
          <p className="mb-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        {isLoading && records.length === 0 ? (
          <LoadingState label="Loading attendance..." />
        ) : (
          <div className="scrollbar-thin overflow-x-auto rounded-xl border border-line/30">
            <table className="w-full text-left text-sm">
              <thead className="bg-glass/40 font-mono text-xs uppercase text-muted">
                <tr>
                  <th className="sticky left-0 z-10 bg-glass/60 px-3 py-2.5 font-medium backdrop-blur">
                    Person
                  </th>
                  {days.map((day) => {
                    const { weekday, date } = dayLabel(day);
                    return (
                      <th
                        key={day}
                        className={`px-2 py-2.5 text-center font-medium ${
                          day === today ? "text-accent" : ""
                        }`}
                      >
                        <div>{weekday}</div>
                        <div className="text-[10px] opacity-70">{date}</div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {people.map((person) => (
                  <tr key={person.id} className="border-t border-line/20">
                    <td className="sticky left-0 z-10 bg-glass/40 px-3 py-2 backdrop-blur">
                      <button
                        type="button"
                        onClick={() => onOpenProfile?.(person.id)}
                        className="flex items-center gap-2 text-left"
                      >
                        <Avatar name={person.name} team={person.team} size={26} />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-text">{person.name}</p>
                          <TeamBadge team={person.team} className="text-[9px]" />
                        </div>
                      </button>
                    </td>
                    {days.map((day) => {
                      const status = grid.get(`${person.id}|${day}`) ?? "unmarked";
                      const key = `${person.id}|${day}`;
                      return (
                        <td key={day} className="px-1 py-2 text-center">
                          <button
                            type="button"
                            onClick={() => cycle(person, day)}
                            disabled={saving === key}
                            title={`${person.name} · ${day} · ${FULL[status]} (click to change)`}
                            aria-label={`${person.name} on ${day}: ${FULL[status]}`}
                            className={`h-7 w-7 rounded-lg border text-xs font-semibold transition hover:scale-110 disabled:opacity-50 ${CELL[status].className}`}
                          >
                            {CELL[status].short}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-3 text-xs text-muted">
          Click any cell to cycle Present → Absent → Leave → Half day → Remote. Or just ask:{" "}
          <span className="text-text-2">“mark the QA team present today”</span>.
        </p>
      </div>
    </div>
  );
}
