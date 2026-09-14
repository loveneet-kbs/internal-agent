import { useEffect, useState } from "react";
import { Check, Mail, Pencil, Send, X } from "lucide-react";
import { sendMail, errorMessage } from "../services/api.js";

/**
 * Renders an agent-drafted email and holds it until a human approves.
 *
 * The agent can compose but never deliver: sending is this component posting to
 * /api/mail/send, which requires the admin token. A prompt alone cannot send mail.
 */
export default function EmailApproval({ draft, onSent }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [isEditing, setIsEditing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [discarded, setDiscarded] = useState(false);
  const [error, setError] = useState("");

  // A new draft replaces whatever was on screen, including any unsent edits.
  useEffect(() => {
    setSubject(draft.subject);
    setBody(draft.body);
    setIsEditing(false);
    setIsSending(false);
    setSent(false);
    setDiscarded(false);
    setError("");
  }, [draft]);

  const handleSend = async () => {
    if (isSending || sent) return;
    setError("");
    setIsSending(true);
    try {
      await sendMail({ to: draft.to, subject, body });
      setSent(true);
      onSent?.();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to send the email."));
    } finally {
      setIsSending(false);
    }
  };

  if (discarded) {
    return (
      <p className="rounded-lg border border-line/25 bg-glass/25 px-4 py-3 text-sm text-muted">
        Draft discarded. Nothing was sent.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-accent/25 bg-glass/25">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line/25 bg-accent/8 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <Mail size={14} className="flex-shrink-0 text-accent" />
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted">To</span>
          <span className="truncate text-sm text-text-2">
            {draft.to_name ? `${draft.to_name} · ` : ""}
            <span className="font-mono text-xs text-muted">{draft.to}</span>
          </span>
        </div>
        {!sent && (
          <span className="flex-shrink-0 rounded-full border border-warning/30 bg-warning/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-warning">
            Awaiting your approval
          </span>
        )}
      </div>

      <div className="space-y-3 p-4">
        <div>
          <label
            htmlFor="draft-subject"
 className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-muted"
          >
            Subject
          </label>
          {isEditing ? (
            <input
              id="draft-subject"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
 className="w-full rounded-lg border border-line/30 bg-glass/40 px-3 py-2 text-sm text-text outline-none focus:border-accent/60 focus:bg-glass/60"
            />
          ) : (
            <p className="text-base font-medium text-text">{subject}</p>
          )}
        </div>

        <div>
          <label
            htmlFor="draft-body"
 className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-muted"
          >
            Message
          </label>
          {isEditing ? (
            <textarea
              id="draft-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={12}
 className="w-full resize-y rounded-lg border border-line/30 bg-glass/40 px-3 py-2 text-sm leading-7 text-text outline-none focus:border-accent/60 focus:bg-glass/60"
            />
          ) : (
            <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg border border-line/25 bg-glass/20 p-4 text-sm leading-7 text-text-2 scrollbar-thin">
              {body}
            </div>
          )}
        </div>

        {error && (
          <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}

        {sent ? (
          <p className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2.5 text-sm text-success">
            <Check size={15} /> Sent to {draft.to}.
          </p>
        ) : (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleSend}
              disabled={isSending || !subject.trim() || !body.trim()}
 className="flex items-center gap-2 btn-accent rounded-xl px-4 py-2.5 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send size={15} />
              {isSending ? "Sending..." : "Approve & send"}
            </button>
            <button
              type="button"
              onClick={() => setIsEditing((previous) => !previous)}
 className="flex items-center gap-2 rounded-lg border border-line/30 px-3 py-2.5 text-sm text-muted transition hover:border-accent/50 hover:text-accent"
            >
              {isEditing ? <Check size={14} /> : <Pencil size={14} />}
              {isEditing ? "Done editing" : "Edit"}
            </button>
            <button
              type="button"
              onClick={() => setDiscarded(true)}
 className="flex items-center gap-2 rounded-lg border border-line/30 px-3 py-2.5 text-sm text-muted transition hover:border-danger/40 hover:text-danger"
            >
              <X size={14} /> Discard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
