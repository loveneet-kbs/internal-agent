import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ClipboardList, RefreshCw, User } from "lucide-react";
import { Avatar, TeamBadge, TEAMS } from "./TeamBadge.jsx";
import LoadingState from "./LoadingState.jsx";
import { completeWorkTask, errorMessage, getWorkTasks } from "../services/api.js";

export const PRIORITY_STYLE = {
  urgent: "text-danger border-danger/40 bg-danger/10",
  high: "text-warning border-warning/40 bg-warning/10",
  medium: "text-info border-info/35 bg-info/10",
  low: "text-muted border-line/35 bg-glass/25"
};

export const STATUS_STYLE = {
  todo: "text-muted border-line/35 bg-glass/25",
  in_progress: "text-accent border-accent/35 bg-accent/10",
  blocked: "text-danger border-danger/35 bg-danger/10",
  done: "text-success border-success/35 bg-success/10",
  cancelled: "text-muted border-line/35 bg-glass/20"
};

export const STATUS_LABEL = {
  todo: "To do",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled"
};

export function formatDue(value) {
  if (!value) return null;
  const d = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", timeZone: "UTC" });
}

/** One task row. `onComplete` enables the tick button. */
export function TaskRow({ task, onComplete, onOpenProfile }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(task.status === "done");

  const finish = async () => {
    setBusy(true);
    try {
      await onComplete?.(task);
      setDone(true);
    } finally {
      setBusy(false);
    }
  };

  const status = done ? "done" : task.status;

  return (
    <li className="rounded-xl border border-line/20 bg-glass/20 px-3 py-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-start gap-2.5">
          {onComplete && status !== "done" && status !== "cancelled" ? (
            <button
              type="button"
              onClick={finish}
              disabled={busy}
              title="Mark complete"
              aria-label={`Complete ${task.title}`}
              className="mt-0.5 flex-shrink-0 rounded-full border border-line/40 p-0.5 text-muted transition hover:border-success/50 hover:text-success disabled:opacity-40"
            >
              <CheckCircle2 size={15} />
            </button>
          ) : (
            <CheckCircle2
              size={15}
              className={`mt-0.5 flex-shrink-0 ${
                status === "done" ? "text-success" : "text-muted/40"
              }`}
            />
          )}

          <div className="min-w-0">
            <p
              className={`truncate text-sm font-medium ${
                status === "done" ? "text-muted line-through" : "text-text"
              }`}
            >
              {task.title}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
              <span className="font-mono text-[10px]">#{task.id}</span>
              {task.assignee ? (
                <button
                  type="button"
                  onClick={() => onOpenProfile?.(task.assignee_id)}
                  className="flex items-center gap-1 hover:text-accent"
                >
                  <Avatar name={task.assignee} team={task.assignee_team} size={16} />
                  {task.assignee}
                </button>
              ) : (
                <span className="flex items-center gap-1 italic">
                  <User size={11} /> unassigned
                </span>
              )}
              {task.due_date && (
                <span className={task.overdue ? "font-medium text-danger" : ""}>
                  {task.overdue && <AlertTriangle size={10} className="mr-0.5 inline" />}
                  due {formatDue(task.due_date)}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-shrink-0 items-center gap-1.5">
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
              PRIORITY_STYLE[task.priority] || PRIORITY_STYLE.medium
            }`}
          >
            {task.priority}
          </span>
          <span
            className={`rounded-full border px-2 py-0.5 text-xs ${
              STATUS_STYLE[status] || STATUS_STYLE.todo
            }`}
          >
            {STATUS_LABEL[status] || status}
          </span>
          {task.team && <TeamBadge team={task.team} />}
        </div>
      </div>

      {task.description && (
        <p className="mt-1.5 pl-6 text-xs leading-5 text-muted">{task.description}</p>
      )}
    </li>
  );
}

const FILTERS = [
  { id: "open", label: "Open", params: { open_only: true } },
  { id: "overdue", label: "Overdue", params: { overdue_only: true } },
  { id: "unassigned", label: "Unassigned", params: { unassigned: true } },
  { id: "done", label: "Done", params: { status: "done" } },
  { id: "all", label: "All", params: {} }
];

export default function TaskBoard({ onOpenProfile }) {
  const [filter, setFilter] = useState("open");
  const [team, setTeam] = useState("All");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const preset = FILTERS.find((f) => f.id === filter)?.params ?? {};
      const { data } = await getWorkTasks({
        ...preset,
        ...(team === "All" ? {} : { team })
      });
      setRows(data.data);
      setSummary(data.summary);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load tasks."));
    } finally {
      setIsLoading(false);
    }
  }, [filter, team]);

  useEffect(() => {
    load();
  }, [load]);

  const complete = async (task) => {
    await completeWorkTask(task.id);
    await load();
  };

  const tiles = useMemo(
    () =>
      summary
        ? [
            { label: "Open", value: summary.open },
            { label: "Overdue", value: summary.overdue, tone: "text-danger" },
            { label: "Urgent", value: summary.urgent_open, tone: "text-warning" },
            { label: "Done", value: summary.done, tone: "text-success" }
          ]
        : [],
    [summary]
  );

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">
            Workload
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-text">Tasks</h2>
          <p className="mt-1 text-sm text-muted">
            {summary
              ? `${summary.total} total · ${summary.completion_rate ?? 0}% complete`
              : "Work assigned across the team."}
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="glass glass-hover flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-text-2 hover:text-accent"
        >
          <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tiles.map((tile) => (
            <div key={tile.label} className="glass rounded-2xl px-4 py-3">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted">
                {tile.label}
              </p>
              <p className={`mt-0.5 text-lg font-semibold ${tile.tone || "text-text"}`}>
                {tile.value}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="glass rounded-2xl p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setFilter(item.id)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                  filter === item.id
                    ? "border-accent/45 bg-accent/12 text-accent"
                    : "border-line/30 text-muted hover:text-text-2"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {["All", ...TEAMS].map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => setTeam(name)}
                className={`rounded-full px-2 py-1 text-xs transition ${
                  team === name ? "text-accent" : "text-muted hover:text-text-2"
                }`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="mb-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        {isLoading && rows.length === 0 ? (
          <LoadingState label="Loading tasks..." />
        ) : rows.length === 0 ? (
          <div className="py-10 text-center">
            <ClipboardList size={22} className="mx-auto mb-2 text-muted" />
            <p className="text-sm text-muted">Nothing here.</p>
          </div>
        ) : (
          <ul className="space-y-1.5">
            {rows.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                onComplete={complete}
                onOpenProfile={onOpenProfile}
              />
            ))}
          </ul>
        )}

        <p className="mt-3 text-xs text-muted">
          Or just ask:{" "}
          <span className="text-text-2">“create a task to audit contrast for Sana, due Friday”</span>
        </p>
      </div>
    </div>
  );
}
