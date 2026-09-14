import { Moon, Sun } from "lucide-react";
import useTheme from "../hooks/useTheme.js";

/** Sliding light/dark switch. The knob carries the icon so the state is legible
 *  at a glance, not just by colour. */
export default function ThemeToggle() {
  const { toggle, isDark } = useTheme();

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={isDark}
      aria-label={`Switch to ${isDark ? "light" : "dark"} mode`}
      title={`Switch to ${isDark ? "light" : "dark"} mode`}
      className="glass glass-hover group relative flex h-9 w-[4.25rem] flex-shrink-0 items-center rounded-full px-1"
    >
      {/* Rail icons - the inactive one stays visible but dimmed. */}
      <span className="pointer-events-none absolute inset-0 flex items-center justify-between px-2">
        <Sun
          size={13}
          className={`transition-opacity duration-300 ${isDark ? "opacity-35 text-muted" : "opacity-0"}`}
        />
        <Moon
          size={13}
          className={`transition-opacity duration-300 ${isDark ? "opacity-0" : "opacity-35 text-muted"}`}
        />
      </span>

      {/* Knob */}
      <span
        className="relative flex h-7 w-7 items-center justify-center rounded-full shadow-lg transition-transform duration-300 ease-[cubic-bezier(0.34,1.3,0.64,1)]"
        style={{
          background: "linear-gradient(135deg, rgb(var(--accent-soft)), rgb(var(--accent)))",
          transform: isDark ? "translateX(2.25rem)" : "translateX(0)"
        }}
      >
        {isDark ? (
          <Moon size={14} className="text-white" />
        ) : (
          <Sun size={14} className="text-white" />
        )}
      </span>
    </button>
  );
}
