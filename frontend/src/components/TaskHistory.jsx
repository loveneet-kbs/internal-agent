import { useEffect, useState } from "react";
import StatusBadge from "./StatusBadge.jsx";
import { History, X, Trash2 } from "lucide-react";
import { deleteTask, errorMessage } from "../services/api.js";

function formatDate(value) {
  if (!value) return "";
  return new Date(`${value}Z`).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default function TaskHistory({ tasks, onRefresh }) {
  const [selected, setSelected] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  // Escape closes the detail dialog.
  useEffect(() => {
    if (!selected) return undefined;
    const onKey = (event) => event.key === "Escape" && setSelected(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  const handleDelete = async (task) => {
    if (!window.confirm(`Delete task #${task.id} from history?`)) return;
    setDeletingId(task.id);
    try {
      await deleteTask(task.id);
      if (selected?.id === task.id) setSelected(null);
      await onRefresh?.();
    } catch (error) {
      window.alert(errorMessage(error, "Unable to delete task history."));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="glass rounded-2xl p-5">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-text">
        <History size={15} className="text-accent" /> TASK HISTORY
      </h2>

      {(!tasks || tasks.length === 0) && <p className="text-sm text-muted">No tasks run yet.</p>}

      <ul className="scrollbar-thin max-h-80 space-y-2 overflow-y-auto pr-1">
        {tasks?.map((task) => (
          // Sibling buttons, not a button inside a button - the latter is invalid
          // HTML and breaks keyboard and screen-reader navigation.
          <li
            key={task.id}
            className="glass-hover flex items-stretch gap-1 rounded-xl border border-line/25 bg-glass/25"
          >
            <button
              type="button"
              onClick={() => setSelected(task)}
              className="min-w-0 flex-1 rounded-l-xl px-3 py-2.5 text-left"
            >
              <p className="truncate text-sm text-text-2">{task.prompt}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-muted">
                  {task.tool_name || task.intent || "—"}
                </span>
                <StatusBadge status={task.status} />
                <span className="text-[11px] text-muted">{formatDate(task.created_at)}</span>
              </div>
            </button>
            <button
              type="button"
              title={`Delete task #${task.id}`}
              aria-label={`Delete task #${task.id}`}
              disabled={deletingId === task.id}
              onClick={() => handleDelete(task)}
              className="rounded-r-xl px-2.5 text-muted transition-colors hover:bg-danger/12 hover:text-danger disabled:opacity-50"
            >
              <Trash2 size={13} className={deletingId === task.id ? "animate-pulse" : ""} />
            </button>
          </li>
        ))}
      </ul>

      {selected && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Task ${selected.id} details`}
          className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
          onClick={() => setSelected(null)}
        >
          <div
            onClick={(event) => event.stopPropagation()}
            className="glass-strong scrollbar-thin max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl p-5"
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-text">Task #{selected.id}</h3>
              <button
                type="button"
                onClick={() => setSelected(null)}
                aria-label="Close"
                className="rounded-lg p-1 text-muted transition-colors hover:bg-glass/50 hover:text-text"
              >
                <X size={16} />
              </button>
            </div>
            <dl className="space-y-2.5 text-sm">
              <Row label="Original Prompt" value={selected.prompt} />
              <Row label="Intent" value={selected.intent} mono />
              <Row label="Tools" value={selected.tool_name} mono />
              <Row label="Parameters" value={JSON.stringify(selected.parameters ?? {})} mono />
              <Row
                label="Endpoint"
                value={selected.endpoint ? `${selected.method} ${selected.endpoint}` : "—"}
                mono
              />
              <Row label="Status" value={<StatusBadge status={selected.status} />} />
              <Row
                label="Result"
                value={JSON.stringify(selected.result ?? selected.error ?? "—")}
                mono
              />
              <Row label="Timestamp" value={formatDate(selected.created_at)} />
            </dl>
            {/* Inside the card. It used to sit outside it, so it rendered beside
                the dialog and its click bubbled up and dismissed the modal. */}
            <button
              type="button"
              onClick={() => handleDelete(selected)}
              disabled={deletingId === selected.id}
              className="mt-5 flex items-center gap-2 rounded-xl border border-danger/30 px-3 py-2 text-xs font-medium text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
            >
              <Trash2 size={13} />
              {deletingId === selected.id ? "Deleting..." : "Delete history"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className={`col-span-2 break-words text-text-2 ${mono ? "font-mono text-xs" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
