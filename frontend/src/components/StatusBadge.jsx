import { CheckCircle2, XCircle, Loader2, HelpCircle, CircleDashed } from "lucide-react";

const STYLES = {
  completed: { icon: CheckCircle2, tone: "success" },
  running: { icon: Loader2, tone: "accent", spin: true },
  pending: { icon: CircleDashed, tone: "muted" },
  failed: { icon: XCircle, tone: "danger" },
  needs_information: { icon: HelpCircle, tone: "warning" },
  unsupported: { icon: XCircle, tone: "danger" }
};

const LABELS = {
  completed: "Completed",
  running: "Running",
  pending: "Pending",
  failed: "Failed",
  needs_information: "Needs Information",
  unsupported: "Unsupported"
};

// Tone -> classes. Written out rather than interpolated so Tailwind's scanner
// can see every class name it needs to emit.
const TONES = {
  success: "text-success border-success/35 bg-success/10",
  accent: "text-accent border-accent/35 bg-accent/10",
  muted: "text-muted border-line/40 bg-glass/20",
  danger: "text-danger border-danger/35 bg-danger/10",
  warning: "text-warning border-warning/35 bg-warning/10"
};

export default function StatusBadge({ status = "pending", size = "sm" }) {
  const config = STYLES[status] || STYLES.pending;
  const Icon = config.icon;
  const pad = size === "lg" ? "px-3 py-1.5 text-sm" : "px-2 py-0.5 text-xs";

  return (
    <span
      className={`inline-flex flex-shrink-0 items-center gap-1.5 rounded-full border font-mono font-medium ${pad} ${
        TONES[config.tone]
      }`}
    >
      <Icon size={size === "lg" ? 14 : 12} className={config.spin ? "animate-spin" : ""} />
      {LABELS[status] || status}
    </span>
  );
}
