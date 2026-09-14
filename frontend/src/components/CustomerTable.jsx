import { useMemo, useState } from "react";
import { Database, RefreshCw, RotateCcw, Search, Trash2, Users } from "lucide-react";
import { Avatar, StatusChip, TeamBadge, TEAMS } from "./TeamBadge.jsx";
import { deleteCustomer, errorMessage, restoreCustomer } from "../services/api.js";

export default function CustomerTable({ customers, onRefresh, isLoading, onOpenProfile }) {
  const [team, setTeam] = useState("All");
  const [query, setQuery] = useState("");
  const [undo, setUndo] = useState(null);
  const [error, setError] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (customers ?? []).filter((person) => {
      if (team !== "All" && person.team !== team) return false;
      if (!needle) return true;
      return [person.name, person.email, person.title, person.location]
        .filter(Boolean)
        .some((field) => field.toLowerCase().includes(needle));
    });
  }, [customers, team, query]);

  const counts = useMemo(() => {
    const map = { All: customers?.length ?? 0 };
    for (const person of customers ?? []) {
      const key = person.team || "Unassigned";
      map[key] = (map[key] ?? 0) + 1;
    }
    return map;
  }, [customers]);

  const handleDelete = async (person) => {
    if (!window.confirm(`Delete ${person.name}? You can undo this.`)) return;
    setError("");
    try {
      await deleteCustomer(person.id);
      setUndo(person); // soft delete, so offer the way back
      await onRefresh();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to delete this employee."));
    }
  };

  const handleUndo = async () => {
    if (!undo) return;
    try {
      await restoreCustomer(undo.id);
      setUndo(null);
      await onRefresh();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to restore."));
    }
  };

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-text">
          <Database size={15} className="text-accent" /> EMPLOYEE DIRECTORY
          <span className="glass rounded-full px-2 py-0.5 font-mono text-[10px] text-muted">
            {visible.length}
            {visible.length !== counts.All ? ` / ${counts.All}` : ""}
          </span>
        </h2>
        <button
          type="button"
          onClick={onRefresh}
          className="glass glass-hover flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-text-2 hover:text-accent"
        >
          <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12rem] flex-1">
          <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by name, email, title or city..."
            className="w-full rounded-xl border border-line/30 bg-glass/40 py-2 pl-8 pr-3 text-sm text-text outline-none transition placeholder:text-muted/70 focus:border-accent/60 focus:bg-glass/60"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {["All", ...TEAMS].map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setTeam(name)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                team === name
                  ? "border-accent/45 bg-accent/12 text-accent"
                  : "border-line/30 text-muted hover:text-text-2"
              }`}
            >
              {name}
              {counts[name] ? <span className="ml-1 opacity-60">{counts[name]}</span> : null}
            </button>
          ))}
        </div>
      </div>

      {undo && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
          <span className="text-text-2">
            <strong className="text-text">{undo.name}</strong> moved to the recycle bin.
          </span>
          <button
            type="button"
            onClick={handleUndo}
            className="flex items-center gap-1.5 rounded-lg border border-warning/40 px-2.5 py-1 text-xs font-medium text-warning transition hover:bg-warning/10"
          >
            <RotateCcw size={12} /> Undo
          </button>
        </div>
      )}

      {error && (
        <p className="mb-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="scrollbar-thin overflow-x-auto rounded-xl border border-line/30">
        <table className="w-full text-left text-sm">
          <thead className="bg-glass/40 font-mono text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2.5 font-medium">Person</th>
              <th className="px-3 py-2.5 font-medium">Team</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Contact</th>
              <th className="hidden px-3 py-2.5 font-medium lg:table-cell">Location</th>
              <th className="px-3 py-2.5 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.length ? (
              visible.map((person) => (
                <tr
                  key={person.id}
                  className="cursor-pointer border-t border-line/20 text-text-2 transition-colors hover:bg-glass/30"
                  onClick={() => onOpenProfile?.(person.id)}
                >
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <Avatar name={person.name} team={person.team} size={34} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-text">{person.name}</p>
                        <p className="truncate text-xs text-muted">{person.title || "—"}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-1">
                      <TeamBadge team={person.team} />
                      <StatusChip status={person.status} />
                    </div>
                  </td>
                  <td className="hidden px-3 py-2.5 md:table-cell">
                    <p className="truncate font-mono text-xs">{person.email}</p>
                    <p className="truncate font-mono text-xs text-muted">{person.phone || "—"}</p>
                  </td>
                  <td className="hidden px-3 py-2.5 text-xs lg:table-cell">
                    {person.location || "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button
                      type="button"
                      title={`Delete ${person.name}`}
                      aria-label={`Delete ${person.name}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDelete(person);
                      }}
                      className="rounded-lg p-1.5 text-muted transition-colors hover:bg-danger/12 hover:text-danger"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="px-3 py-10 text-center">
                  <Users size={22} className="mx-auto mb-2 text-muted" />
                  <p className="text-sm text-muted">
                    {counts.All ? "No one matches those filters." : "No employees yet."}
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
