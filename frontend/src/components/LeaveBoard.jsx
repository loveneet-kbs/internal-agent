import { useCallback, useEffect, useState } from "react";
import { CalendarClock, RefreshCw } from "lucide-react";
import { LeaveView } from "./ResultViews.jsx";
import LoadingState from "./LoadingState.jsx";
import { approveLeave, errorMessage, getLeaveRequests, rejectLeave } from "../services/api.js";

const FILTERS = ["pending", "approved", "rejected", "all"];

/** Every leave request, filterable, with approve/reject inline. */
export default function LeaveBoard({ onOpenProfile, onDecided }) {
  const [status, setStatus] = useState("pending");
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const { data } = await getLeaveRequests(status === "all" ? {} : { status });
      setRows(data.data);
      setSummary(data.summary);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load leave requests."));
    } finally {
      setIsLoading(false);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const decide = async (request, approve, note) => {
    if (approve) await approveLeave(request.id, note);
    else await rejectLeave(request.id, note);
    await load();
    await onDecided?.();
  };

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">
            Time off
          </p>
          <h2 className="text-2xl font-semibold tracking-tight text-text">Leave requests</h2>
          <p className="mt-1 text-sm text-muted">
            {summary
              ? `${summary.pending} pending · ${summary.approved} approved · ${summary.rejected} rejected`
              : "Approve or reject time off, or ask the agent to do it."}
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

      <div className="glass rounded-2xl p-5">
        <div className="mb-4 flex flex-wrap gap-1.5">
          {FILTERS.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setStatus(name)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium capitalize transition ${
                status === name
                  ? "border-accent/45 bg-accent/12 text-accent"
                  : "border-line/30 text-muted hover:text-text-2"
              }`}
            >
              {name}
              {summary && name !== "all" && summary[name] ? (
                <span className="ml-1 opacity-60">{summary[name]}</span>
              ) : null}
            </button>
          ))}
        </div>

        {error && (
          <p className="mb-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        {isLoading && rows.length === 0 ? (
          <LoadingState label="Loading leave requests..." />
        ) : rows.length === 0 ? (
          <div className="py-10 text-center">
            <CalendarClock size={22} className="mx-auto mb-2 text-muted" />
            <p className="text-sm text-muted">
              {status === "pending" ? "Nothing waiting for approval." : `No ${status} requests.`}
            </p>
          </div>
        ) : (
          <LeaveView rows={rows} onDecide={decide} onOpenProfile={onOpenProfile} />
        )}
      </div>
    </div>
  );
}
