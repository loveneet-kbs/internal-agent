import { Workflow } from "lucide-react";
import ThemeToggle from "./ThemeToggle.jsx";

export default function Header({ connected }) {
  return (
    <header className="glass sticky top-0 z-30 flex items-center justify-between gap-4 rounded-none border-x-0 border-t-0 px-4 py-3 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <div
          className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl shadow-lg"
          style={{
            background: "linear-gradient(135deg, rgb(var(--accent-soft)), rgb(var(--accent)))",
            boxShadow: "0 8px 20px -8px rgb(var(--accent-soft) / 0.8)"
          }}
        >
          <Workflow size={19} className="text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold tracking-tight text-text">AI Task Agent</h1>
          <p className="hidden truncate text-xs text-muted sm:block">
            Give instructions in plain English and let AI run the right tools.
          </p>
        </div>
      </div>

      <div className="flex flex-shrink-0 items-center gap-2.5">
        <div className="glass hidden items-center gap-2 rounded-full px-3 py-1.5 sm:flex">
          <span className="relative flex h-2 w-2">
            {connected && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
            )}
            <span
              className={`relative inline-flex h-2 w-2 rounded-full ${
                connected ? "bg-success" : "bg-danger"
              }`}
            />
          </span>
          <span className="font-mono text-xs font-medium text-text-2">
            {connected ? "Connected" : "Offline"}
          </span>
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
