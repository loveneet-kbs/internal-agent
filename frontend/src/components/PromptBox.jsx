import { useState } from "react";
import { Sparkles, ArrowRight, Search, UserPlus, Pencil, Mail, Send, Loader2 } from "lucide-react";

const EXAMPLES = [
  { label: "Show employees", prompt: "Show me all employees", icon: Search },
  { label: "Find someone", prompt: "Find employee Rahul Sharma", icon: Search },
  {
    label: "Add employee",
    prompt:
      "Add a new employee named Aisha Khan with email aisha.khan@example.com and phone 9876544444",
    icon: UserPlus
  },
  {
    label: "Update details",
    prompt: "Update employee 3's email to priya.singh@newmail.com",
    icon: Pencil
  },
  {
    label: "Email someone",
    prompt:
      "Send an email to Rahul Sharma letting him know the project is delayed by two weeks and the new deadline is 15 September",
    icon: Send
  },
  {
    label: "Add + email",
    prompt:
      "Add an employee named Iris Chen with email iris.chen@example.com, then email her that orientation is Tuesday 9 September at 10am in Room 2B",
    icon: Sparkles
  },
  { label: "Mail Studio", action: "mail", icon: Mail }
];

const MAX_CHARS = 2000;

export default function PromptBox({ onRun, onOpenMail, isRunning }) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);

  const trimmed = value.trim();
  const tooLong = value.length > MAX_CHARS;
  const canRun = Boolean(trimmed) && !isRunning && !tooLong;

  const submit = () => {
    if (!canRun) return;
    onRun(trimmed);
  };

  const handleKeyDown = (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div
      className={`glass-strong relative overflow-hidden rounded-2xl p-5 transition-shadow duration-300 ${
        focused ? "ring-1 ring-accent/40" : ""
      }`}
    >
      {/* Sweeping highlight while a task runs */}
      {isRunning && (
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-0.5 animate-shimmer"
          style={{
            backgroundImage:
              "linear-gradient(90deg, transparent, rgb(var(--accent-soft)), transparent)",
            backgroundSize: "200% 100%"
          }}
        />
      )}

      <div className="relative mb-3 flex items-start justify-between gap-4">
        <label
          htmlFor="agent-prompt"
          className="flex items-center gap-2 text-sm font-semibold text-text"
        >
          <span
            className="flex h-7 w-7 items-center justify-center rounded-lg"
            style={{
              background: "linear-gradient(135deg, rgb(var(--accent-soft)), rgb(var(--accent)))"
            }}
          >
            <Sparkles size={14} className="text-white" />
          </span>
          What would you like me to do?
        </label>
        <span className="glass hidden flex-shrink-0 rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-muted sm:block">
          AI command center
        </span>
      </div>

      <textarea
        id="agent-prompt"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        rows={4}
        placeholder="e.g. Add Rahul with email rahul@gmail.com, then email him a welcome note"
        className="relative w-full resize-none rounded-xl border border-line/35 bg-glass/40 px-4 py-3 text-sm leading-6 text-text outline-none transition placeholder:text-muted/70 focus:border-accent/60 focus:bg-glass/60"
      />

      <div className="mt-1.5 flex items-center justify-between">
        <p className="text-[11px] text-muted">
          Tip: press <kbd className="font-mono text-text-2">Ctrl</kbd> +{" "}
          <kbd className="font-mono text-text-2">Enter</kbd> to run
        </p>
        {value.length > MAX_CHARS * 0.75 && (
          <span className={`font-mono text-[11px] ${tooLong ? "text-danger" : "text-muted"}`}>
            {value.length} / {MAX_CHARS}
          </span>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted">
            Quick commands
          </p>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map(({ label, prompt, action, icon: Icon }) => (
              <button
                key={label}
                type="button"
                onClick={() => (action === "mail" ? onOpenMail?.() : setValue(prompt))}
                title={action === "mail" ? "Open Mail Studio" : prompt}
                className="glass glass-hover flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-text-2 hover:text-accent"
              >
                <Icon size={12} />
                {label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={submit}
          disabled={!canRun}
          className="btn-accent flex flex-shrink-0 items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed"
        >
          {isRunning ? (
            <>
              <Loader2 size={15} className="animate-spin" /> Running...
            </>
          ) : (
            <>
              Run Task <ArrowRight size={15} />
            </>
          )}
        </button>
      </div>
    </div>
  );
}
