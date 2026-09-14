import { useState } from "react";
import { Check, Clipboard, Mail, Send, Sparkles } from "lucide-react";
import { generateMail, sendMail, errorMessage } from "../services/api.js";

const PURPOSES = [
  "Leave approval request",
  "Meeting request",
  "Project update",
  "Follow-up reminder",
  "Thank-you note",
  "Custom message"
];

const TONES = ["Professional", "Friendly", "Formal", "Concise"];

export default function MailStudio({ customers = [], onSent }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [purpose, setPurpose] = useState(PURPOSES[0]);
  const [details, setDetails] = useState("");
  const [tone, setTone] = useState(TONES[0]);
  const [draft, setDraft] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async (event) => {
    event.preventDefault();
    setIsGenerating(true);
    setError("");
    setSent(false);
    setCopied(false);
    try {
      const { data } = await generateMail({ recipient: to, purpose, details, tone: tone.toLowerCase() });
      setDraft(data.data);
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to generate the email draft."));
    } finally {
      setIsGenerating(false);
    }
  };

  const copyDraft = async () => {
    if (!draft) return;
    await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleSend = async () => {
    if (!draft || isSending) return;
    setError("");
    setSent(false);
    setIsSending(true);
    try {
      await sendMail({ from, to, subject: draft.subject, body: draft.body });
      setSent(true);
      onSent?.();
    } catch (requestError) {
      setError(errorMessage(requestError, "Unable to send the email."));
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.24em] text-accent/80">Communication workspace</p>
          <h2 className="text-2xl font-semibold tracking-tight text-text">Write the right message</h2>
          <p className="mt-1 text-sm text-muted">Shape the context. AI will turn it into a ready-to-send email.</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-line/30 bg-glass/40 px-3 py-2 font-mono text-xs text-muted">
          <Mail size={14} className="text-accent" /> SMTP delivery
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <form onSubmit={handleGenerate} className="glass rounded-2xl p-5 ">
          <div className="mb-5 flex items-center gap-3 border-b border-line/30 pb-4">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 text-accent"><Sparkles size={17} /></div>
            <div>
              <h3 className="text-sm font-semibold text-text">Draft an email</h3>
              <p className="text-xs text-muted">Review the generated message before sending.</p>
            </div>
          </div>
          <label className="mb-1.5 block text-xs font-medium text-muted">Reply-to</label>
          <input value={from} onChange={(event) => setFrom(event.target.value)} placeholder="you@company.com" required className="mb-1.5 w-full rounded-lg border border-line/30 bg-glass/40 px-3 py-2.5 text-sm text-text outline-none transition placeholder:text-muted focus:border-accent/60 focus:bg-glass/60" />
          <p className="mb-4 text-[11px] leading-4 text-muted">Mail is always sent from the configured SMTP account; this address is set as Reply-To.</p>
          <label className="mb-1.5 block text-xs font-medium text-muted">To</label>
          <input
            list="customer-emails"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            placeholder="name@company.com"
            required
 className="mb-4 w-full rounded-lg border border-line/30 bg-glass/40 px-3 py-2.5 text-sm text-text outline-none transition placeholder:text-muted focus:border-accent/60 focus:bg-glass/60"
          />
          <datalist id="customer-emails">{customers.map((customer) => <option key={customer.id} value={customer.email}>{customer.name}</option>)}</datalist>

          <label className="mb-1.5 block text-xs font-medium text-muted">What is this about?</label>
          <select value={purpose} onChange={(event) => setPurpose(event.target.value)} className="mb-4 w-full rounded-lg border border-line/30 bg-glass/40 px-3 py-2.5 text-sm text-text outline-none focus:border-accent">
            {PURPOSES.map((item) => <option key={item}>{item}</option>)}
          </select>

          <label className="mb-1.5 block text-xs font-medium text-muted">Tone</label>
          <div className="mb-4 grid grid-cols-4 gap-1.5 rounded-lg border border-line/30 bg-glass/40 p-1">
            {TONES.map((item) => <button type="button" key={item} onClick={() => setTone(item)} className={`rounded-md px-2 py-1.5 text-xs transition ${tone === item ? "bg-accent/20 text-accent" : "text-muted hover:text-text-2"}`}>{item}</button>)}
          </div>

          <label className="mb-1.5 block text-xs font-medium text-muted">Key details</label>
          <textarea value={details} onChange={(event) => setDetails(event.target.value)} rows={6} placeholder="Add dates, context, the action you need, or any details the recipient should know..." className="mb-4 w-full resize-none rounded-lg border border-line/30 bg-glass/40 px-3 py-2.5 text-sm leading-6 text-text outline-none transition placeholder:text-muted focus:border-accent/60 focus:bg-glass/60" />
          {error && <p className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>}
          <button disabled={isGenerating} className="flex w-full items-center justify-center gap-2 btn-accent rounded-xl px-4 py-2.5 text-sm font-semibold disabled:cursor-wait disabled:opacity-60">
            <Sparkles size={15} /> {isGenerating ? "Writing draft..." : "Generate email"}
          </button>
        </form>

        <section className="glass min-h-[520px] rounded-2xl p-5 ">
          <div className="mb-5 flex items-center justify-between border-b border-line/30 pb-4">
            <div><p className="font-mono text-[10px] uppercase tracking-widest text-muted">Preview</p><h3 className="mt-1 text-sm font-semibold text-text">Your email draft</h3></div>
            {draft && <button type="button" onClick={copyDraft} title="Copy email" className="flex items-center gap-1.5 rounded-lg border border-line/30 px-2.5 py-1.5 text-xs text-muted hover:border-accent/50 hover:text-accent">{copied ? <Check size={13} /> : <Clipboard size={13} />}{copied ? "Copied" : "Copy"}</button>}
          </div>
          {draft ? (
            <div className="flex h-[calc(100%-4.5rem)] flex-col">
              <div className="mb-5 rounded-lg border border-line/25 bg-glass/30 p-4"><p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-muted">Subject</p><p className="text-base font-medium text-text">{draft.subject}</p></div>
              <div className="flex-1 whitespace-pre-wrap rounded-lg border border-line/25 bg-glass/20 p-4 text-sm leading-7 text-text-2">{draft.body}</div>
              <button type="button" onClick={handleSend} disabled={isSending} className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-4 py-2.5 text-sm font-semibold text-accent transition hover:bg-accent/20 disabled:cursor-wait disabled:opacity-60"><Send size={15} /> {isSending ? "Sending..." : "Send email"}</button>
              {sent && <p className="mt-3 text-center text-xs text-success">Email sent successfully.</p>}
            </div>
          ) : <div className="flex h-[calc(100%-4.5rem)] flex-col items-center justify-center text-center"><div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/25 bg-accent/10 text-accent"><Mail size={24} /></div><p className="text-sm font-medium text-text-2">Your draft will appear here</p><p className="mt-1 max-w-xs text-xs leading-5 text-muted">Choose a purpose, add a little context, and let the writing assistant handle the first pass.</p></div>}
        </section>
      </div>
    </div>
  );
}
