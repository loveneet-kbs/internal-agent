import { CheckCircle2, XCircle, Loader2, CircleDashed, HelpCircle, Zap } from "lucide-react";

const PIPELINE = ["Prompt", "Groq LLM", "Tool", "API", "Database", "Result"];

function iconFor(status) {
  if (status === "completed") return <CheckCircle2 size={14} className="text-success" />;
  if (status === "failed" || status === "unsupported")
    return <XCircle size={14} className="text-danger" />;
  if (status === "needs_information") return <HelpCircle size={14} className="text-warning" />;
  if (status === "running") return <Loader2 size={14} className="animate-spin text-accent" />;
  return <CircleDashed size={14} className="text-muted" />;
}

export default function TaskExecution({ steps, activeStage, isRunning }) {
  const hasContent = steps && steps.length > 0;

  return (
    <div className="glass rounded-2xl p-5">
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold tracking-wide text-text">
        <Zap size={15} className="text-accent" /> TASK EXECUTION
      </h2>

      {/* The live pipeline chain */}
      <div className="scrollbar-thin mb-5 flex items-center overflow-x-auto pb-1">
        {PIPELINE.map((stage, index) => {
          const isActive = index <= activeStage;
          const isCurrent = index === activeStage && isRunning;
          return (
            <div key={stage} className="flex flex-shrink-0 items-center">
              <div
                className={`rounded-xl border px-3 py-1.5 font-mono text-xs transition-all duration-300 ${
                  isActive
                    ? "border-accent/45 bg-accent/12 text-accent"
                    : "border-line/30 bg-glass/25 text-muted"
                } ${isCurrent ? "animate-pulse-soft" : ""}`}
                style={
                  isCurrent
                    ? { boxShadow: "0 0 16px -2px rgb(var(--accent-soft) / 0.5)" }
                    : undefined
                }
              >
                {stage}
              </div>
              {index < PIPELINE.length - 1 && (
                <div
                  className={`h-px w-6 flex-shrink-0 transition-colors duration-300 ${
                    index < activeStage ? "bg-accent/60" : "bg-line/30"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      {!hasContent && (
        <p className="text-sm text-muted">Run a task to see live execution steps here.</p>
      )}

      {hasContent && (
        <ul className="space-y-2">
          {steps.map((step, index) => (
            <li
              key={`${step.label}-${index}`}
              className="flex animate-slide-in items-start gap-2.5 rounded-xl border border-line/25 bg-glass/25 px-3 py-2 text-sm"
              style={{ animationDelay: `${Math.min(index * 40, 320)}ms`, animationFillMode: "backwards" }}
            >
              <span className="mt-0.5 flex-shrink-0">{iconFor(step.status)}</span>
              <div className="min-w-0">
                <p className="text-text-2">{step.label}</p>
                {step.detail && (
                  <p className="mt-0.5 break-words font-mono text-xs text-muted">{step.detail}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
