import { useState } from "react";
import { Mail, X } from "lucide-react";

function formatDate(value) {
  if (!value) return "";
  return new Date(`${value}Z`).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default function SentMail({ messages = [] }) {
  const [selected, setSelected] = useState(null);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">Communication history</p>
          <h2 className="text-2xl font-semibold tracking-tight text-text">Sent Mail</h2>
          <p className="mt-1 text-sm text-muted">Review messages delivered through your configured SMTP account.</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-line/30 bg-glass/40 px-3 py-2 font-mono text-xs text-muted">
          <Mail size={14} className="text-success" /> {messages.length} sent
        </div>
      </div>

      <section className="overflow-hidden glass rounded-2xl ">
        {messages.length === 0 ? (
          <div className="flex min-h-72 flex-col items-center justify-center px-6 text-center">
            <Mail size={26} className="mb-3 text-muted" />
            <p className="text-sm font-medium text-text-2">No sent mail yet</p>
            <p className="mt-1 text-xs text-muted">Messages sent from Mail Studio will appear here.</p>
          </div>
        ) : (
          <div className="divide-y divide-glass/40">
            {messages.map((message) => (
              <button key={message.id} type="button" onClick={() => setSelected(message)} className="flex w-full flex-wrap items-center justify-between gap-3 px-5 py-4 text-left transition hover:bg-glass/40">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text-2">{message.subject}</p>
                  <p className="mt-1 truncate font-mono text-xs text-muted">To: {message.recipient}</p>
                </div>
                <div className="text-right">
                  <p className="font-mono text-[11px] text-success">Delivered</p>
                  <p className="mt-1 text-[11px] text-muted">{formatDate(message.sent_at)}</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSelected(null)}>
          <div className="w-full max-w-2xl glass rounded-2xl p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="mb-5 flex items-start justify-between border-b border-line/30 pb-4">
              <div><p className="font-mono text-[10px] uppercase tracking-widest text-muted">Sent message</p><h3 className="mt-1 text-base font-semibold text-text">{selected.subject}</h3></div>
              <button type="button" onClick={() => setSelected(null)} title="Close message"><X size={16} className="text-muted hover:text-text-2" /></button>
            </div>
            <div className="mb-4 grid gap-2 rounded-lg border border-line/25 bg-glass/25 p-4 font-mono text-xs"><p><span className="text-muted">From: </span><span className="text-text-2">{selected.sender}</span></p><p><span className="text-muted">To: </span><span className="text-text-2">{selected.recipient}</span></p><p><span className="text-muted">Sent: </span><span className="text-text-2">{formatDate(selected.sent_at)}</span></p></div>
            <div className="whitespace-pre-wrap rounded-lg border border-line/25 bg-glass/20 p-4 text-sm leading-7 text-text-2">{selected.body}</div>
          </div>
        </div>
      )}
    </div>
  );
}
