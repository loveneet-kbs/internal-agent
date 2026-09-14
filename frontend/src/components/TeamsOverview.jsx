import { Users } from "lucide-react";
import { Avatar, StatusChip, TeamBadge, TEAMS } from "./TeamBadge.jsx";

/** Headcount per team, with the people grouped underneath. */
export default function TeamsOverview({ customers = [], stats, onOpenProfile }) {
  const grouped = TEAMS.map((team) => ({
    team,
    people: customers.filter((person) => person.team === team)
  })).filter((group) => group.people.length > 0);

  const unassigned = customers.filter((person) => !person.team);
  if (unassigned.length) grouped.push({ team: null, people: unassigned });

  const total = stats?.total ?? customers.length;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div className="px-1">
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">
          Organisation
        </p>
        <h2 className="text-2xl font-semibold tracking-tight text-text">Teams</h2>
        <p className="mt-1 text-sm text-muted">
          {total} people across {grouped.length} teams
          {stats?.on_leave ? ` · ${stats.on_leave} on leave` : ""}
          {stats?.alumni ? ` · ${stats.alumni} alumni` : ""}
          {stats?.in_recycle_bin ? ` · ${stats.in_recycle_bin} in the recycle bin` : ""}
        </p>
      </div>

      {grouped.length === 0 && (
        <div className="glass rounded-2xl p-10 text-center">
          <Users size={24} className="mx-auto mb-2 text-muted" />
          <p className="text-sm text-muted">No people yet. Run the seed script to load a demo team.</p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {grouped.map(({ team, people }) => (
          <section key={team ?? "unassigned"} className="glass rounded-2xl p-5">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <TeamBadge team={team} />
                <span className="text-sm font-semibold text-text">
                  {people.length} {people.length === 1 ? "person" : "people"}
                </span>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
                {people.filter((p) => p.status === "active").length} active
              </span>
            </div>

            <ul className="space-y-1.5">
              {people.map((person) => (
                <li key={person.id}>
                  <button
                    type="button"
                    onClick={() => onOpenProfile?.(person.id)}
                    className="flex w-full items-center gap-2.5 rounded-xl border border-line/20 bg-glass/20 px-2.5 py-2 text-left transition-colors hover:border-accent/35 hover:bg-glass/40"
                  >
                    <Avatar name={person.name} team={person.team} size={30} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-text">{person.name}</p>
                      <p className="truncate text-xs text-muted">{person.title || "—"}</p>
                    </div>
                    <StatusChip status={person.status} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
