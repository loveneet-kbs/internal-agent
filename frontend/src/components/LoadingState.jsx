import { Loader2 } from "lucide-react";

export default function LoadingState({ label = "Loading..." }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted">
      <Loader2 size={16} className="animate-spin text-accent" />
      <span className="font-mono">{label}</span>
    </div>
  );
}
