import { useState } from "react";
import {
  CalendarDays,
  ChevronDown,
  Mail,
  StickyNote,
  Table2,
  Users,
  AlertTriangle,
  AlertCircle,
  BarChart3,
  PieChart,
  Calendar,
  Clock,
  Video,
  Sparkles,
  ArrowRight,
  ShieldAlert,
  Info,
  CheckCircle2
} from "lucide-react";
import { Avatar, StatusChip, TeamBadge } from "./TeamBadge.jsx";
import { TaskRow } from "./TaskBoard.jsx";

/**
 * Renders a tool result as a readable answer rather than a raw dump.
 *
 * Each shape gets its own view; the underlying table is always one click away for
 * when you actually want the columns.
 */

const HIDDEN = ["is_seed", "deleted_at", "updated_at"];
const PREFERRED = ["id", "name", "title", "team", "status", "email", "phone", "location"];

function cell(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value.length <= 10 ? `${value}T00:00:00Z` : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

/** Detect what a tool handed back so the right view can render it. */
export function shapeOf(result) {
  const data = result?.data;
  if (!data) return "empty";
  if (Array.isArray(data)) {
    if (data.length === 0) return "empty-list";
    const first = data[0];
    if (first?.title !== undefined && first?.priority !== undefined) return "work-tasks";
    if (first?.start_time !== undefined && first?.attendees !== undefined) return "meetings";
    if (first?.day !== undefined && first?.status !== undefined && first?.person !== undefined)
      return "attendance";
    if (first?.leave_type !== undefined && first?.start_date !== undefined) return "leave";
    if (first?.name && first?.email !== undefined) return "people";
    if (first?.body !== undefined && first?.customer_id !== undefined) return "notes";
    if (first?.subject !== undefined && first?.recipient !== undefined) return "mail";
    return "rows";
  }
  if (data.summary !== undefined && Array.isArray(data.anomalies)) return "anomalies";
  if (data.metric !== undefined && data.chart_type !== undefined && Array.isArray(data.items)) return "chart";
  if (data.start_time !== undefined && data.attendees !== undefined && data.title !== undefined) return "meeting";
  if (data.available_slots_count !== undefined && Array.isArray(data.slots)) return "free-slots";
  if (data.kind === "email_draft") return "draft";
  if (data.profile !== undefined && data.tasks !== undefined) return "snapshot";
  if (data.title !== undefined && data.priority !== undefined) return "work-task";
  if (data.scope !== undefined && data.open !== undefined) return "task-summary";
  if (data.leave_type !== undefined && data.start_date !== undefined) return "leave-one";
  if (data.day !== undefined && data.headcount !== undefined) return "attendance-summary";
  if (data.day !== undefined && data.status !== undefined) return "attendance-one";
  if (Array.isArray(data.teams)) return "stats";
  if (data.name && data.email !== undefined) return "person";
  return "object";
}

// --------------------------------------------------------------------------- //
// Raw table, kept behind a toggle
// --------------------------------------------------------------------------- //
function RawTable({ rows }) {
  const present = new Set();
  for (const row of rows) for (const key of Object.keys(row)) present.add(key);
  HIDDEN.forEach((key) => present.delete(key));
  const ordered = PREFERRED.filter((k) => present.has(k));
  const columns = [...ordered, ...[...present].filter((k) => !ordered.includes(k)).sort()];

  return (
    <div className="scrollbar-thin max-h-80 overflow-auto rounded-xl border border-line/30">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-glass/60 font-mono text-xs uppercase text-muted backdrop-blur">
          <tr>
            {columns.map((col) => (
              <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                {col.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id ?? index} className="border-t border-line/20 text-text-2">
              {columns.map((col) => (
                <td key={col} className="whitespace-nowrap px-3 py-2 font-mono text-xs">
                  {cell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RawToggle({ rows, label = "table" }) {
  const [open, setOpen] = useState(false);
  if (!rows?.length) return null;
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((previous) => !previous)}
        className="flex items-center gap-1.5 text-xs font-medium text-muted transition-colors hover:text-accent"
      >
        <Table2 size={12} />
        {open ? "Hide" : "Show"} {label}
        <ChevronDown
          size={12}
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="mt-2">
          <RawTable rows={rows} />
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// People
// --------------------------------------------------------------------------- //
const COLLAPSE_AFTER = 8;

export function PeopleView({ rows, onOpenProfile }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, COLLAPSE_AFTER);
  const hidden = rows.length - shown.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {shown.map((person) => (
          <li key={person.id}>
            <button
              type="button"
              onClick={() => onOpenProfile?.(person.id)}
              className="flex w-full items-center gap-2.5 rounded-xl border border-line/20 bg-glass/20 px-2.5 py-2 text-left transition-colors hover:border-accent/35 hover:bg-glass/40"
            >
              <Avatar name={person.name} team={person.team} size={30} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text">{person.name}</p>
                <p className="truncate text-xs text-muted">
                  {[person.title, person.location].filter(Boolean).join(" · ") || person.email}
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-1.5">
                <StatusChip status={person.status} />
                <TeamBadge team={person.team} />
              </div>
            </button>
          </li>
        ))}
      </ul>

      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs font-medium text-accent hover:underline"
        >
          Show {hidden} more
        </button>
      )}

      <RawToggle rows={rows} />
    </div>
  );
}

export function PersonView({ person, onOpenProfile }) {
  return <PeopleView rows={[person]} onOpenProfile={onOpenProfile} />;
}

// --------------------------------------------------------------------------- //
// Notes
// --------------------------------------------------------------------------- //
export function NotesView({ rows }) {
  return (
    <div>
      <ul className="space-y-1.5">
        {rows.map((note) => (
          <li
            key={note.id}
            className="rounded-xl border border-line/20 bg-glass/20 px-3 py-2.5"
          >
            <p className="flex items-start gap-2 text-sm text-text-2">
              <StickyNote size={13} className="mt-0.5 flex-shrink-0 text-accent" />
              <span className="break-words">{note.body}</span>
            </p>
            <p className="mt-1 pl-5 font-mono text-[10px] text-muted">
              {note.author} · {formatDate(note.created_at)}
            </p>
          </li>
        ))}
      </ul>
      <RawToggle rows={rows} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Sent mail
// --------------------------------------------------------------------------- //
export function MailView({ rows }) {
  return (
    <div>
      <ul className="space-y-1.5">
        {rows.map((message) => (
          <li
            key={message.id}
            className="rounded-xl border border-line/20 bg-glass/20 px-3 py-2.5"
          >
            <div className="flex items-start gap-2">
              <Mail size={13} className="mt-0.5 flex-shrink-0 text-accent" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text">{message.subject}</p>
                <p className="truncate font-mono text-xs text-muted">
                  To {message.recipient} · {formatDate(message.sent_at)}
                </p>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <RawToggle rows={rows} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Team stats
// --------------------------------------------------------------------------- //
export function StatsView({ data }) {
  const max = Math.max(1, ...data.teams.map((team) => team.headcount));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {[
          { label: "Total", value: data.total, icon: Users },
          { label: "Active", value: data.active },
          { label: "On leave", value: data.on_leave },
          { label: "Alumni", value: data.alumni },
          { label: "Joined 90d", value: data.joined_last_90_days, icon: CalendarDays }
        ]
          .filter((item) => item.value > 0 || item.label === "Total")
          .map((item) => (
            <div key={item.label} className="glass rounded-xl px-3 py-2">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted">
                {item.label}
              </p>
              <p className="mt-0.5 text-lg font-semibold text-text">{item.value}</p>
            </div>
          ))}
      </div>

      <ul className="space-y-1.5">
        {data.teams.map((team) => (
          <li key={team.team} className="flex items-center gap-3">
            <span className="w-24 flex-shrink-0 text-sm text-text-2">{team.team}</span>
            <span className="h-2 flex-1 overflow-hidden rounded-full bg-glass/40">
              <span
                className="block h-full rounded-full transition-all duration-500"
                style={{
                  width: `${(team.headcount / max) * 100}%`,
                  background:
                    "linear-gradient(90deg, rgb(var(--accent-soft)), rgb(var(--accent)))"
                }}
              />
            </span>
            <span className="w-8 flex-shrink-0 text-right font-mono text-xs text-muted">
              {team.headcount}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Fallbacks
// --------------------------------------------------------------------------- //
export function ObjectView({ data }) {
  const entries = Object.entries(data).filter(([key]) => !HIDDEN.includes(key));
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 rounded-xl border border-line/30 bg-glass/25 p-4 font-mono text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <span className="text-muted">{key.replace(/_/g, " ")}</span>
          <span className="break-words text-text-2">{cell(value)}</span>
        </div>
      ))}
    </div>
  );
}

export function RowsView({ rows }) {
  return <RawTable rows={rows} />;
}

// --------------------------------------------------------------------------- //
// Leave requests
// --------------------------------------------------------------------------- //
const LEAVE_STATUS = {
  pending: "text-warning border-warning/35 bg-warning/10",
  approved: "text-success border-success/35 bg-success/10",
  rejected: "text-danger border-danger/35 bg-danger/10",
  cancelled: "text-muted border-line/40 bg-glass/30"
};

const LEAVE_TYPE_LABEL = {
  annual: "Annual",
  sick: "Sick",
  casual: "Casual",
  unpaid: "Unpaid",
  parental: "Parental"
};

function range(request) {
  const from = formatDate(request.start_date);
  const to = formatDate(request.end_date);
  return from === to ? from : `${from} → ${to}`;
}

/** One leave request. Pending ones can be decided inline. */
export function LeaveRow({ request, onDecide, onOpenProfile }) {
  const [busy, setBusy] = useState("");
  const [reason, setReason] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(null);

  const status = done ?? request.status;
  const pending = status === "pending";

  const decide = async (approve) => {
    if (!approve && !reason.trim()) {
      setAsking(true);
      return;
    }
    setBusy(approve ? "approve" : "reject");
    setError("");
    try {
      await onDecide?.(request, approve, reason.trim());
      setDone(approve ? "approved" : "rejected");
      setAsking(false);
    } catch (requestError) {
      setError(requestError?.message || "Could not record that decision.");
    } finally {
      setBusy("");
    }
  };

  return (
    <li className="rounded-xl border border-line/20 bg-glass/20 px-3 py-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <button
          type="button"
          onClick={() => onOpenProfile?.(request.customer_id)}
          className="flex min-w-0 items-center gap-2.5 text-left"
        >
          <Avatar name={request.person} team={request.team} size={30} />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-text">{request.person}</p>
            <p className="truncate text-xs text-muted">
              {LEAVE_TYPE_LABEL[request.leave_type] || request.leave_type} ·{" "}
              {request.days} day{request.days === 1 ? "" : "s"} · {range(request)}
            </p>
          </div>
        </button>

        <div className="flex flex-shrink-0 items-center gap-1.5">
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
              LEAVE_STATUS[status] || LEAVE_STATUS.cancelled
            }`}
          >
            {status}
          </span>
          <span className="font-mono text-[10px] text-muted">#{request.id}</span>
        </div>
      </div>

      {request.reason && (
        <p className="mt-1.5 pl-[2.6rem] text-xs italic text-muted">“{request.reason}”</p>
      )}

      {request.decision_note && !pending && (
        <p className="mt-1.5 pl-[2.6rem] text-xs text-muted">
          Note: {request.decision_note}
        </p>
      )}

      {error && <p className="mt-2 pl-[2.6rem] text-xs text-danger">{error}</p>}

      {pending && onDecide && (
        <div className="mt-2 pl-[2.6rem]">
          {asking && (
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Reason for rejecting (required)"
              autoFocus
              className="mb-2 w-full rounded-lg border border-line/30 bg-glass/40 px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent/60"
            />
          )}
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              disabled={Boolean(busy)}
              onClick={() => decide(true)}
              className="rounded-lg border border-success/40 bg-success/10 px-2.5 py-1 text-xs font-medium text-success transition hover:bg-success/20 disabled:opacity-50"
            >
              {busy === "approve" ? "Approving..." : "Approve"}
            </button>
            <button
              type="button"
              disabled={Boolean(busy)}
              onClick={() => decide(false)}
              className="rounded-lg border border-danger/40 px-2.5 py-1 text-xs font-medium text-danger transition hover:bg-danger/10 disabled:opacity-50"
            >
              {busy === "reject" ? "Rejecting..." : asking ? "Confirm reject" : "Reject"}
            </button>
            {asking && (
              <button
                type="button"
                onClick={() => {
                  setAsking(false);
                  setReason("");
                }}
                className="rounded-lg px-2.5 py-1 text-xs text-muted hover:text-text-2"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

export function LeaveView({ rows, onDecide, onOpenProfile }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, COLLAPSE_AFTER);
  const hidden = rows.length - shown.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {shown.map((request) => (
          <LeaveRow
            key={request.id}
            request={request}
            onDecide={onDecide}
            onOpenProfile={onOpenProfile}
          />
        ))}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs font-medium text-accent hover:underline"
        >
          Show {hidden} more
        </button>
      )}
      <RawToggle rows={rows} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Attendance
// --------------------------------------------------------------------------- //
const ATT_STYLE = {
  present: "text-success border-success/35 bg-success/10",
  absent: "text-danger border-danger/35 bg-danger/10",
  leave: "text-warning border-warning/35 bg-warning/10",
  half_day: "text-info border-info/35 bg-info/10",
  wfh: "text-accent border-accent/35 bg-accent/10"
};

const ATT_LABEL = {
  present: "Present",
  absent: "Absent",
  leave: "Leave",
  half_day: "Half day",
  wfh: "Remote"
};

export function AttendanceView({ rows, onOpenProfile }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, COLLAPSE_AFTER);
  const hidden = rows.length - shown.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {shown.map((record) => (
          <li key={record.id}>
            <button
              type="button"
              onClick={() => onOpenProfile?.(record.customer_id)}
              className="flex w-full items-center gap-2.5 rounded-xl border border-line/20 bg-glass/20 px-2.5 py-2 text-left transition-colors hover:border-accent/35 hover:bg-glass/40"
            >
              <Avatar name={record.person} team={record.team} size={30} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text">{record.person}</p>
                <p className="truncate text-xs text-muted">
                  {formatDate(record.day)}
                  {record.note ? ` · ${record.note}` : ""}
                </p>
              </div>
              <span
                className={`flex-shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${
                  ATT_STYLE[record.status] || ATT_STYLE.present
                }`}
              >
                {ATT_LABEL[record.status] || record.status}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs font-medium text-accent hover:underline"
        >
          Show {hidden} more
        </button>
      )}
      <RawToggle rows={rows} />
    </div>
  );
}

export function AttendanceSummaryView({ data, onOpenProfile }) {
  const tiles = [
    { key: "present", label: "Present" },
    { key: "absent", label: "Absent" },
    { key: "leave", label: "Leave" },
    { key: "half_day", label: "Half day" },
    { key: "wfh", label: "Remote" }
  ].filter((tile) => data[tile.key] > 0);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {tiles.map((tile) => (
          <div key={tile.key} className={`rounded-xl border px-3 py-2 ${ATT_STYLE[tile.key]}`}>
            <p className="font-mono text-[10px] uppercase tracking-widest opacity-80">
              {tile.label}
            </p>
            <p className="mt-0.5 text-lg font-semibold">{data[tile.key]}</p>
          </div>
        ))}
      </div>

      {data.unmarked > 0 && (
        <div className="rounded-xl border border-line/25 bg-glass/20 p-3">
          <p className="mb-2 text-xs font-medium text-muted">
            {data.unmarked} not marked on {formatDate(data.day)}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {data.unmarked_people?.slice(0, 12).map((person) => (
              <button
                key={person.id}
                type="button"
                onClick={() => onOpenProfile?.(person.id)}
                className="rounded-full border border-line/30 px-2 py-0.5 text-xs text-text-2 transition hover:border-accent/40 hover:text-accent"
              >
                {person.name}
              </button>
            ))}
            {data.unmarked_people?.length > 12 && (
              <span className="text-xs text-muted">
                +{data.unmarked_people.length - 12} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Work tasks + employee snapshot
// --------------------------------------------------------------------------- //
export function WorkTasksView({ rows, onComplete, onOpenProfile }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, COLLAPSE_AFTER);
  const hidden = rows.length - shown.length;

  return (
    <div>
      <ul className="space-y-1.5">
        {shown.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            onComplete={onComplete}
            onOpenProfile={onOpenProfile}
          />
        ))}
      </ul>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs font-medium text-accent hover:underline"
        >
          Show {hidden} more
        </button>
      )}
      <RawToggle rows={rows} />
    </div>
  );
}

export function TaskSummaryView({ data }) {
  const tiles = [
    { label: "Total", value: data.total },
    { label: "Open", value: data.open },
    { label: "Done", value: data.done, tone: "text-success" },
    { label: "Overdue", value: data.overdue, tone: "text-danger" },
    { label: "Urgent", value: data.urgent_open, tone: "text-warning" }
  ].filter((tile) => tile.value > 0 || tile.label === "Total");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {tiles.map((tile) => (
          <div key={tile.label} className="glass rounded-xl px-3 py-2">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted">
              {tile.label}
            </p>
            <p className={`mt-0.5 text-lg font-semibold ${tile.tone || "text-text"}`}>
              {tile.value}
            </p>
          </div>
        ))}
      </div>
      {data.completion_rate !== null && (
        <div>
          <div className="mb-1 flex justify-between text-xs text-muted">
            <span>{data.scope}</span>
            <span>{data.completion_rate}% complete</span>
          </div>
          <span className="block h-2 overflow-hidden rounded-full bg-glass/40">
            <span
              className="block h-full rounded-full transition-all duration-500"
              style={{
                width: `${data.completion_rate}%`,
                background: "linear-gradient(90deg, rgb(var(--success)), rgb(var(--accent)))"
              }}
            />
          </span>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="glass rounded-xl px-3 py-2">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className={`mt-0.5 text-base font-semibold ${tone || "text-text"}`}>{value}</p>
    </div>
  );
}

export function SnapshotView({ data, onOpenProfile }) {
  const { profile, manager, direct_reports: reports, attendance, leave, tasks, notes } = data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Avatar name={profile.name} team={profile.team} size={48} />
        <div className="min-w-0">
          <p className="text-lg font-semibold text-text">{profile.name}</p>
          <p className="text-sm text-muted">
            {[profile.title, profile.location].filter(Boolean).join(" · ")}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <TeamBadge team={profile.team} />
            <StatusChip status={profile.status} />
            {profile.tenure && (
              <span className="text-xs text-muted">{profile.tenure} at the company</span>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Stat label="Open tasks" value={tasks.open} />
        {tasks.overdue > 0 && <Stat label="Overdue" value={tasks.overdue} tone="text-danger" />}
        {attendance.attendance_rate !== null && (
          <Stat label="Attendance" value={`${attendance.attendance_rate}%`} />
        )}
        {leave.pending_count > 0 && (
          <Stat label="Leave pending" value={leave.pending_count} tone="text-warning" />
        )}
        {reports.length > 0 && <Stat label="Reports" value={reports.length} />}
      </div>

      {(manager || reports.length > 0) && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          {manager && (
            <span>
              Reports to{" "}
              <button
                type="button"
                onClick={() => onOpenProfile?.(manager.id)}
                className="text-accent hover:underline"
              >
                {manager.name}
              </button>
            </span>
          )}
          {reports.length > 0 && (
            <span className="flex flex-wrap items-center gap-1">
              Manages
              {reports.slice(0, 6).map((person) => (
                <button
                  key={person.id}
                  type="button"
                  onClick={() => onOpenProfile?.(person.id)}
                  className="rounded-full border border-line/30 px-2 py-0.5 hover:border-accent/40 hover:text-accent"
                >
                  {person.name}
                </button>
              ))}
              {reports.length > 6 && <span>+{reports.length - 6}</span>}
            </span>
          )}
        </div>
      )}

      {tasks.open_items?.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted">
            Open work
          </p>
          <ul className="space-y-1.5">
            {tasks.open_items.slice(0, 5).map((task) => (
              <TaskRow key={task.id} task={task} onOpenProfile={onOpenProfile} />
            ))}
          </ul>
        </div>
      )}

      {leave.pending.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted">
            Leave awaiting a decision
          </p>
          <LeaveView rows={leave.pending} onOpenProfile={onOpenProfile} />
        </div>
      )}

      {notes.length > 0 && (
        <div>
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-muted">
            Notes
          </p>
          <NotesView rows={notes} />
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Tool 1: Anomaly Radar & Proactive Intelligence
// --------------------------------------------------------------------------- //
export function AnomalyRadarView({ data, onRunPrompt }) {
  const summary = data?.summary || {};
  const anomalies = data?.anomalies || [];

  return (
    <div className="space-y-4">
      {/* Header Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/20 bg-glass/30 p-3">
        <div className="flex items-center gap-2">
          <ShieldAlert size={18} className="text-warning" />
          <div>
            <h4 className="font-semibold text-xs text-text">Workspace Anomaly & Risk Radar</h4>
            <p className="text-[11px] text-muted">Active scan of tasks, team capacity, and leave collisions</p>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="rounded-lg bg-danger/15 px-2.5 py-1 text-danger font-semibold">
            {summary.critical_count || 0} Critical
          </span>
          <span className="rounded-lg bg-warning/15 px-2.5 py-1 text-warning font-semibold">
            {summary.warning_count || 0} Warnings
          </span>
          <span className="rounded-lg bg-info/15 px-2.5 py-1 text-info font-semibold">
            {summary.info_count || 0} Info
          </span>
        </div>
      </div>

      {/* Anomaly list */}
      <div className="space-y-2.5">
        {anomalies.map((item) => {
          const isCritical = item.severity === "critical";
          const isWarning = item.severity === "warning";
          const borderTone = isCritical
            ? "border-danger/40 bg-danger/5"
            : isWarning
            ? "border-warning/40 bg-warning/5"
            : "border-info/30 bg-info/5";

          return (
            <div
              key={item.id}
              className={`flex flex-col justify-between gap-2.5 rounded-xl border p-3.5 transition-all ${borderTone}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  {isCritical ? (
                    <AlertTriangle size={15} className="text-danger flex-shrink-0" />
                  ) : isWarning ? (
                    <AlertCircle size={15} className="text-warning flex-shrink-0" />
                  ) : (
                    <Info size={15} className="text-info flex-shrink-0" />
                  )}
                  <span className="font-semibold text-xs text-text">{item.title}</span>
                </div>

                <div className="flex items-center gap-1.5">
                  {item.team && <TeamBadge team={item.team} />}
                  <span className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded bg-glass text-muted">
                    {item.category}
                  </span>
                </div>
              </div>

              <p className="text-xs text-text-2">{item.description}</p>

              {item.prompt_template && (
                <div className="flex items-center justify-between border-t border-line/15 pt-2">
                  <span className="text-[11px] text-muted italic truncate max-w-sm">
                    Suggested action: {item.suggested_action}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (onRunPrompt) onRunPrompt(item.prompt_template);
                      else alert(`Run prompt: "${item.prompt_template}" in the chat box above.`);
                    }}
                    className="flex items-center gap-1 text-xs font-semibold text-accent hover:underline flex-shrink-0 ml-2"
                  >
                    <span>Fix with Agent</span>
                    <ArrowRight size={12} />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Tool 4: Dynamic Interactive Charts & Visualizations
// --------------------------------------------------------------------------- //
export function ChartView({ data }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const items = data?.items || [];
  const chartType = data?.chart_type || "bar";
  const total = data?.total || items.reduce((acc, it) => acc + (it.value || 0), 0);

  return (
    <div className="space-y-4 rounded-2xl border border-line/25 bg-glass/25 p-4">
      {/* Chart Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-1.5">
            {chartType === "donut" || chartType === "pie" ? (
              <PieChart size={15} className="text-accent" />
            ) : (
              <BarChart3 size={15} className="text-accent" />
            )}
            <h4 className="font-semibold text-sm text-text">{data?.title || "Analytics Chart"}</h4>
          </div>
          {data?.subtitle && <p className="text-xs text-muted mt-0.5">{data.subtitle}</p>}
        </div>

        <div className="rounded-xl border border-line/30 bg-glass/40 px-3 py-1 text-right">
          <p className="font-mono text-[9px] uppercase tracking-wider text-muted">Total Count</p>
          <p className="font-mono text-sm font-semibold text-accent">{total}</p>
        </div>
      </div>

      {/* Donut Chart Rendering */}
      {(chartType === "donut" || chartType === "pie") && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 items-center">
          {/* SVG Donut */}
          <div className="relative flex items-center justify-center p-2">
            <svg viewBox="0 0 100 100" className="w-36 h-36 transform -rotate-90">
              {(() => {
                let accumulatedPercent = 0;
                return items.map((item, idx) => {
                  const percent = total > 0 ? (item.value / total) * 100 : 0;
                  const strokeDasharray = `${percent} ${100 - percent}`;
                  const strokeDashoffset = -accumulatedPercent;
                  accumulatedPercent += percent;
                  const isHovered = hoveredIdx === idx;

                  return (
                    <circle
                      key={idx}
                      cx="50"
                      cy="50"
                      r="38"
                      fill="transparent"
                      stroke={item.color || "#6366f1"}
                      strokeWidth={isHovered ? "14" : "10"}
                      strokeDasharray={strokeDasharray}
                      strokeDashoffset={strokeDashoffset}
                      pathLength="100"
                      className="transition-all duration-300 cursor-pointer"
                      onMouseEnter={() => setHoveredIdx(idx)}
                      onMouseLeave={() => setHoveredIdx(null)}
                    />
                  );
                });
              })()}
            </svg>
            <div className="absolute flex flex-col items-center justify-center text-center pointer-events-none">
              <span className="font-mono text-base font-bold text-text">
                {hoveredIdx !== null ? items[hoveredIdx]?.value : total}
              </span>
              <span className="font-mono text-[9px] text-muted uppercase">
                {hoveredIdx !== null ? items[hoveredIdx]?.label : "Total"}
              </span>
            </div>
          </div>

          {/* Donut Legend */}
          <div className="space-y-1.5">
            {items.map((item, idx) => {
              const isHovered = hoveredIdx === idx;
              return (
                <div
                  key={idx}
                  onMouseEnter={() => setHoveredIdx(idx)}
                  onMouseLeave={() => setHoveredIdx(null)}
                  className={`flex items-center justify-between rounded-lg p-1.5 text-xs transition ${
                    isHovered ? "bg-glass/80" : "hover:bg-glass/40"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="text-text font-medium">{item.label}</span>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-xs">
                    <span className="text-text-2">{item.value}</span>
                    <span className="text-muted text-[10px]">({item.percentage}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Bar / Distribution Chart Rendering */}
      {chartType !== "donut" && chartType !== "pie" && (
        <div className="space-y-3 pt-2">
          {items.map((item, idx) => {
            const pct = item.percentage || (total > 0 ? ((item.value / total) * 100).toFixed(1) : 0);
            return (
              <div key={idx} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-text">{item.label}</span>
                  <div className="flex items-center gap-2 font-mono text-[11px]">
                    <span className="text-text font-semibold">{item.value}</span>
                    <span className="text-muted">({pct}%)</span>
                  </div>
                </div>

                <div className="h-3 w-full rounded-full bg-background/50 overflow-hidden p-0.5 border border-line/20">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.max(2, Number(pct))}%`,
                      backgroundColor: item.color || "#6366f1",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Tool 6: Calendar Meeting & Free Slots Views
// --------------------------------------------------------------------------- //
export function MeetingView({ meeting, onOpenProfile }) {
  if (!meeting) return null;
  const startFormatted = formatDate(meeting.start_time);
  const startTime = meeting.start_time?.split("T")[1]?.slice(0, 5) || "";
  const endTime = meeting.end_time?.split("T")[1]?.slice(0, 5) || "";

  return (
    <div className="rounded-2xl border border-line/30 bg-glass/30 p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-accent/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-accent">
              {startFormatted}
            </span>
            {meeting.team && <TeamBadge team={meeting.team} />}
          </div>
          <h4 className="mt-1.5 font-semibold text-sm text-text">{meeting.title}</h4>
        </div>

        <span className="font-mono text-xs text-muted flex items-center gap-1">
          <Clock size={12} />
          {startTime} - {endTime}
        </span>
      </div>

      {meeting.description && <p className="text-xs text-muted">{meeting.description}</p>}

      <div className="flex flex-wrap items-center justify-between border-t border-line/20 pt-3 gap-2 text-xs">
        <div className="flex items-center gap-1.5">
          <Video size={13} className="text-accent" />
          <span className="text-muted">{meeting.location_or_link || "Google Meet"}</span>
        </div>

        {meeting.attendees?.length > 0 && (
          <div className="flex items-center gap-1">
            <Users size={12} className="text-muted mr-1" />
            <div className="flex -space-x-1.5">
              {meeting.attendees.map((att, i) => (
                <span key={i} title={typeof att === "object" ? att.name : att}>
                  <Avatar name={typeof att === "object" ? att.name : String(att)} size={20} />
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function MeetingListView({ rows, onOpenProfile }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {rows.map((m) => (
        <MeetingView key={m.id} meeting={m} onOpenProfile={onOpenProfile} />
      ))}
    </div>
  );
}

export function FreeSlotsView({ data, onScheduleSlot }) {
  const slots = data?.slots || [];
  return (
    <div className="space-y-3 rounded-2xl border border-line/25 bg-glass/25 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="font-semibold text-xs text-text">Available Meeting Slots</h4>
          <p className="text-[11px] text-muted">
            Date: {data?.date} ({data?.available_slots_count} of {data?.total_slots} slots free)
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {slots.map((s, idx) => (
          <div
            key={idx}
            className={`rounded-xl border p-2 text-xs transition ${
              s.available
                ? "border-success/30 bg-success/10 text-success"
                : "border-line/20 bg-background/20 opacity-40 text-muted"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-medium">{s.time_label}</span>
              {s.available ? (
                <CheckCircle2 size={12} className="text-success" />
              ) : (
                <AlertCircle size={12} className="text-danger" />
              )}
            </div>
            {s.conflicts?.length > 0 && (
              <p className="mt-1 text-[9px] text-danger truncate">{s.conflicts[0]}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

