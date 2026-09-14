/**
 * Team and status chips, plus the initials avatar.
 *
 * Team colours are written out rather than interpolated so Tailwind's scanner can
 * see every class it needs to emit.
 */

const TEAM_STYLES = {
  Design: "text-danger border-danger/35 bg-danger/10",
  AI: "text-accent border-accent/35 bg-accent/10",
  Development: "text-info border-info/35 bg-info/10",
  QA: "text-warning border-warning/35 bg-warning/10",
  Product: "text-success border-success/35 bg-success/10"
};

const TEAM_GRADIENTS = {
  Design: "linear-gradient(135deg, rgb(var(--danger)), rgb(var(--accent-soft)))",
  AI: "linear-gradient(135deg, rgb(var(--accent-soft)), rgb(var(--accent)))",
  Development: "linear-gradient(135deg, rgb(var(--info)), rgb(var(--accent-soft)))",
  QA: "linear-gradient(135deg, rgb(var(--warning)), rgb(var(--danger)))",
  Product: "linear-gradient(135deg, rgb(var(--success)), rgb(var(--info)))"
};

const FALLBACK = "text-muted border-line/40 bg-glass/30";

const STATUS_LABELS = {
  active: "Active",
  on_leave: "On leave",
  alumni: "Alumni"
};

const STATUS_STYLES = {
  active: "text-success border-success/35 bg-success/10",
  on_leave: "text-warning border-warning/35 bg-warning/10",
  alumni: "text-muted border-line/40 bg-glass/30"
};

export function initials(name = "") {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts.at(-1)?.[0] ?? "")).toUpperCase();
}

export function TeamBadge({ team, className = "" }) {
  if (!team) {
    return (
      <span className={`rounded-full border px-2 py-0.5 text-xs ${FALLBACK} ${className}`}>
        Unassigned
      </span>
    );
  }
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
        TEAM_STYLES[team] || FALLBACK
      } ${className}`}
    >
      {team}
    </span>
  );
}

export function StatusChip({ status }) {
  if (!status || status === "active") return null;
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
        STATUS_STYLES[status] || FALLBACK
      }`}
    >
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export function Avatar({ name, team, size = 40 }) {
  return (
    <span
      aria-hidden="true"
      className="flex flex-shrink-0 items-center justify-center rounded-full font-semibold text-white shadow-lg"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: TEAM_GRADIENTS[team] || "linear-gradient(135deg, #94a3b8, #64748b)"
      }}
    >
      {initials(name)}
    </span>
  );
}

export const TEAMS = ["Design", "AI", "Development", "QA", "Product"];
