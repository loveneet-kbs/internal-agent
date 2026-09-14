import { useCallback, useEffect, useState } from "react";
import {
  Briefcase,
  CalendarDays,
  Mail,
  MapPin,
  Phone,
  Plus,
  StickyNote,
  Trash2,
  X
} from "lucide-react";
import { Avatar, StatusChip, TeamBadge } from "./TeamBadge.jsx";
import LoadingState from "./LoadingState.jsx";
import { addNote, deleteNote, errorMessage, getCustomer } from "../services/api.js";

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value.length <= 10 ? `${value}T00:00:00Z` : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function tenure(joinedAt) {
  if (!joinedAt) return null;
  const start = new Date(`${joinedAt}T00:00:00Z`);
  if (Number.isNaN(start.getTime())) return null;
  const months = Math.max(0, Math.round((Date.now() - start.getTime()) / (1000 * 60 * 60 * 24 * 30.44)));
  if (months < 12) return `${months} mo`;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return rest ? `${years}y ${rest}mo` : `${years}y`;
}

function Field({ icon: Icon, label, value, href }) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon size={14} className="mt-0.5 flex-shrink-0 text-muted" />
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</p>
        {href && value !== "—" ? (
          <a
            href={href}
            className="break-words text-sm text-accent underline-offset-2 hover:underline"
          >
            {value}
          </a>
        ) : (
          <p className="break-words text-sm text-text-2">{value}</p>
        )}
      </div>
    </div>
  );
}

/** Full profile for one person: identity, contact, and their notes. */
export default function CustomerProfile({ customerId, onClose, onEmail }) {
  const [person, setPerson] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const { data } = await getCustomer(customerId);
      setPerson(data.data);
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not load this profile."));
    } finally {
      setIsLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const saveNote = async (event) => {
    event.preventDefault();
    if (!draft.trim() || isSaving) return;
    setIsSaving(true);
    setError("");
    try {
      await addNote(customerId, draft.trim());
      setDraft("");
      await load();
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not save that note."));
    } finally {
      setIsSaving(false);
    }
  };

  const removeNote = async (noteId) => {
    try {
      await deleteNote(customerId, noteId);
      await load();
    } catch (requestError) {
      setError(errorMessage(requestError, "Could not delete that note."));
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Employee profile"
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/45 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="glass-strong scrollbar-thin max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl"
      >
        {isLoading ? (
          <LoadingState label="Loading profile..." />
        ) : !person ? (
          <div className="p-6">
            <p className="text-sm text-danger">{error || "Profile not found."}</p>
            <button type="button" onClick={onClose} className="mt-4 text-sm text-muted underline">
              Close
            </button>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b border-line/25 p-5">
              <div className="flex min-w-0 items-center gap-4">
                <Avatar name={person.name} team={person.team} size={56} />
                <div className="min-w-0">
                  <h2 className="truncate text-xl font-semibold tracking-tight text-text">
                    {person.name}
                  </h2>
                  <p className="mt-0.5 truncate text-sm text-muted">{person.title || "—"}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <TeamBadge team={person.team} />
                    <StatusChip status={person.status} />
                    <span className="font-mono text-[10px] text-muted">ID {person.id}</span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close profile"
                className="rounded-lg p-1.5 text-muted transition-colors hover:bg-glass/50 hover:text-text"
              >
                <X size={17} />
              </button>
            </div>

            {/* Detail grid */}
            <div className="grid gap-4 border-b border-line/25 p-5 sm:grid-cols-2">
              <Field icon={Mail} label="Email" value={person.email} href={`mailto:${person.email}`} />
              <Field icon={Phone} label="Phone" value={person.phone || "—"} />
              <Field icon={MapPin} label="Location" value={person.location || "—"} />
              <Field icon={Briefcase} label="Team" value={person.team || "Unassigned"} />
              <Field
                icon={CalendarDays}
                label="Joined"
                value={
                  person.joined_at
                    ? `${formatDate(person.joined_at)}${tenure(person.joined_at) ? ` · ${tenure(person.joined_at)}` : ""}`
                    : "—"
                }
              />
              <Field icon={CalendarDays} label="Record created" value={formatDate(person.created_at)} />
            </div>

            {/* Notes */}
            <div className="p-5">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-text">
                <StickyNote size={15} className="text-accent" /> Notes
                <span className="glass rounded-full px-2 py-0.5 font-mono text-[10px] text-muted">
                  {person.notes?.length ?? 0}
                </span>
              </h3>

              {error && (
                <p className="mb-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
                  {error}
                </p>
              )}

              <ul className="mb-3 space-y-2">
                {person.notes?.length ? (
                  person.notes.map((note) => (
                    <li
                      key={note.id}
                      className="group flex items-start justify-between gap-2 rounded-xl border border-line/25 bg-glass/25 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="break-words text-sm text-text-2">{note.body}</p>
                        <p className="mt-1 font-mono text-[10px] text-muted">
                          {note.author} · {formatDate(note.created_at)}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeNote(note.id)}
                        aria-label="Delete note"
                        className="rounded-lg p-1 text-muted opacity-0 transition hover:bg-danger/12 hover:text-danger focus-visible:opacity-100 group-hover:opacity-100"
                      >
                        <Trash2 size={13} />
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="rounded-xl border border-line/25 bg-glass/20 px-3 py-4 text-center text-sm text-muted">
                    No notes yet.
                  </li>
                )}
              </ul>

              <form onSubmit={saveNote} className="flex gap-2">
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Add a note about this person..."
                  maxLength={2000}
                  className="min-w-0 flex-1 rounded-xl border border-line/30 bg-glass/40 px-3 py-2.5 text-sm text-text outline-none transition placeholder:text-muted/70 focus:border-accent/60 focus:bg-glass/60"
                />
                <button
                  type="submit"
                  disabled={!draft.trim() || isSaving}
                  className="btn-accent flex items-center gap-1.5 rounded-xl px-3.5 py-2.5 text-sm font-semibold disabled:cursor-not-allowed"
                >
                  <Plus size={15} /> {isSaving ? "Saving" : "Add"}
                </button>
              </form>

              <button
                type="button"
                onClick={() => onEmail?.(person)}
                className="glass glass-hover mt-4 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium text-text-2 hover:text-accent"
              >
                <Mail size={15} /> Draft an email to {person.name.split(" ")[0]}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
