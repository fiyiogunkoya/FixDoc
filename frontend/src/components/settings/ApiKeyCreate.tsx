"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy, KeyRound } from "lucide-react";

import { useCreateApiKey } from "@/lib/hooks/useTeams";
import { cn } from "@/lib/cn";

interface Props {
  teamId: string | undefined;
}

export function ApiKeyCreate({ teamId }: Props) {
  const [name, setName] = useState("");
  const [revealed, setRevealed] = useState<{ token: string; name: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const { mutateAsync, isPending } = useCreateApiKey(teamId);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !teamId) return;
    const resp = await mutateAsync(name.trim());
    setRevealed({ token: resp.token, name: resp.name });
    setName("");
  }

  async function copyToken() {
    if (!revealed) return;
    await navigator.clipboard.writeText(revealed.token);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleCreate} className="flex items-center gap-2">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Key name (e.g. laptop, CI runner)"
          className="flex-1 rounded-md border border-border bg-surface-raised px-3 py-2 text-sm placeholder-fg-dim outline-none transition-colors focus:border-brand/60"
        />
        <button
          type="submit"
          disabled={!name.trim() || isPending || !teamId}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-brand text-white text-sm font-medium shadow-glow-soft transition-all duration-150 hover:bg-brand/90 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <KeyRound className="h-3.5 w-3.5" strokeWidth={2} />
          {isPending ? "Creating…" : "Generate"}
        </button>
      </form>

      <AnimatePresence mode="wait">
        {revealed && (
          <motion.div
            key="reveal"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            className="relative overflow-hidden rounded-xl border border-brand/50 bg-gradient-to-br from-brand/10 via-surface to-surface p-5 shadow-glow"
          >
            {/* Ambient glow pulse — signals "this is the moment" */}
            <div
              aria-hidden
              className="absolute -inset-px rounded-xl"
              style={{
                background:
                  "radial-gradient(circle at top left, rgba(139, 92, 246, 0.15), transparent 60%)",
              }}
            />

            <div className="relative flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-medium text-brand">
                  <KeyRound className="h-3 w-3" strokeWidth={2.5} />
                  New API key · {revealed.name}
                </div>
                <p className="mt-1 text-xs text-fg-muted">
                  Copy this now — it will never be shown again.
                </p>
              </div>
              <button
                onClick={copyToken}
                className={cn(
                  "shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs font-medium transition-all",
                  copied
                    ? "border-accent-emerald/60 bg-accent-emerald/10 text-accent-emerald"
                    : "border-border bg-surface-raised text-fg hover:bg-surface-hover",
                )}
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3" strokeWidth={2.5} />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" strokeWidth={2.5} />
                    Copy
                  </>
                )}
              </button>
            </div>

            {/* Token — monospace, shimmer-animated text so it feels "alive" */}
            <div className="relative mt-4 rounded-lg border border-border bg-[#0c0c0e] p-3.5">
              <code className="font-mono text-[13px] text-fg break-all select-all shimmer-text">
                {revealed.token}
              </code>
            </div>

            <div className="relative mt-4 rounded-lg border border-border bg-surface-raised/60 p-3 text-xs text-fg-muted">
              <div className="font-medium text-fg mb-1">Connect your CLI:</div>
              <code className="font-mono text-fg-muted">
                fixdoc login --token {revealed.token.slice(0, 14)}…
              </code>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* NEXT LEVEL: add a confetti burst with react-confetti or a custom canvas on
   token reveal — it's a micro-celebratory moment that rewards the user for
   completing onboarding, without being cringe if kept brief (<1s). */
