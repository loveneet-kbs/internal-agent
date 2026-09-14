import { Activity } from "lucide-react";

const METHOD_TONES = {
  GET: "text-info",
  POST: "text-success",
  PUT: "text-warning",
  PATCH: "text-warning",
  DELETE: "text-danger"
};

export default function ApiActivity({ activity }) {
  return (
    <div className="glass rounded-2xl p-5">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-text">
        <Activity size={15} className="text-accent" /> API ACTIVITY
      </h2>

      {(!activity || activity.length === 0) && (
        <p className="text-sm text-muted">No API calls yet.</p>
      )}

      <ul className="scrollbar-thin max-h-72 space-y-1.5 overflow-y-auto pr-1 font-mono text-xs">
        {activity?.map((entry) => {
          const ok = entry.status_code >= 200 && entry.status_code < 300;
          return (
            <li
              key={entry.id}
              className="flex items-center justify-between gap-2 rounded-xl border border-line/25 bg-glass/25 px-3 py-2 transition-colors hover:bg-glass/40"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className={`flex-shrink-0 font-semibold ${
                    METHOD_TONES[entry.method] || "text-muted"
                  }`}
                >
                  {entry.method}
                </span>
                <span className="truncate text-text-2">{entry.endpoint}</span>
                {entry.source === "agent" && (
                  <span
                    title="Called by the AI agent"
                    className="flex-shrink-0 rounded-full border border-accent/30 bg-accent/10 px-1.5 text-[10px] text-accent"
                  >
                    agent
                  </span>
                )}
              </div>
              <div className="flex flex-shrink-0 items-center gap-3">
                <span className={ok ? "text-success" : "text-danger"}>{entry.status_code}</span>
                <span className="text-muted">{entry.duration_ms}ms</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
