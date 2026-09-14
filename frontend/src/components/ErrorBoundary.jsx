import { Component } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * Catches render-time crashes so one bad row cannot blank the whole page.
 * Must stay a class component - React has no hook equivalent.
 */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Render error:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-backdrop p-6">
        <div className="glass-strong max-w-md rounded-2xl p-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-danger/30 bg-danger/10 text-danger">
            <AlertTriangle size={22} />
          </div>
          <h1 className="text-base font-semibold text-text">Something broke while rendering</h1>
          <p className="mt-2 text-sm leading-6 text-muted">
            The error is in the browser console. Reloading usually clears it.
          </p>
          <p className="mt-3 break-words rounded-lg border border-line/25 bg-glass/25 p-3 text-left font-mono text-xs text-muted">
            {String(this.state.error?.message || this.state.error)}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
 className="mt-4 btn-accent rounded-xl px-4 py-2 text-sm font-semibold"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
