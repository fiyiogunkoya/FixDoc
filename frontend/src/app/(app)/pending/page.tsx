"use client";

import { motion } from "framer-motion";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";

import { cn } from "@/lib/cn";
import { usePending } from "@/lib/hooks/usePending";
import { useTeams } from "@/lib/hooks/useTeams";

export default function PendingPage() {
  const { data: teams } = useTeams();
  const teamId = teams?.[0]?.id;
  const { data: entries, isLoading } = usePending(teamId);

  const worthy = (entries ?? []).filter((e) => e.worthiness === "memory_worthy");
  const selfExplanatory = (entries ?? []).filter((e) => e.worthiness === "self_explanatory");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Pending errors</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Errors captured by <code className="font-mono text-fg">fixdoc watch</code> that haven't been resolved yet.
        </p>
      </div>

      {isLoading && (
        <div className="rounded-xl border border-border bg-surface px-5 py-8 text-center text-sm text-fg-muted">
          Loading…
        </div>
      )}

      {!isLoading && worthy.length === 0 && selfExplanatory.length === 0 && (
        <div className="rounded-xl border border-border bg-surface px-5 py-16 text-center">
          <CheckCircle2 className="mx-auto h-8 w-8 text-accent-emerald" strokeWidth={1.5} />
          <div className="mt-3 text-sm text-fg">No pending errors.</div>
          <div className="mt-1 text-xs text-fg-dim">All caught up.</div>
        </div>
      )}

      {worthy.length > 0 && (
        <section>
          <h2 className="text-xs font-medium uppercase tracking-wider text-fg-dim mb-3 flex items-center gap-2">
            <AlertCircle className="h-3.5 w-3.5 text-accent-amber" strokeWidth={2} />
            Memory-worthy · {worthy.length}
          </h2>
          <ul className="space-y-2">
            {worthy.map((entry, i) => (
              <PendingRow key={entry.id} entry={entry} delay={i * 0.04} />
            ))}
          </ul>
        </section>
      )}

      {selfExplanatory.length > 0 && (
        <section>
          <h2 className="text-xs font-medium uppercase tracking-wider text-fg-dim mb-3 flex items-center gap-2">
            <Info className="h-3.5 w-3.5 text-fg-dim" strokeWidth={2} />
            Self-explanatory · {selfExplanatory.length}
          </h2>
          <ul className="space-y-2">
            {selfExplanatory.map((entry, i) => (
              <PendingRow key={entry.id} entry={entry} delay={i * 0.02} muted />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function PendingRow({
  entry,
  delay,
  muted,
}: {
  entry: {
    id: string;
    short_message: string;
    resource_address: string | null;
    error_code: string | null;
    error_type: string;
    created_at: string;
  };
  delay: number;
  muted?: boolean;
}) {
  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "rounded-lg border bg-surface px-4 py-3 transition-colors",
        muted ? "border-border-subtle" : "border-border hover:border-border-strong",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className={cn("text-sm truncate", muted ? "text-fg-muted" : "text-fg")}>
            {entry.short_message}
          </div>
          <div className="mt-1 flex items-center gap-2 text-[11px] font-mono text-fg-dim">
            {entry.error_code && (
              <span className="px-1 py-0.5 rounded bg-surface-raised border border-border">
                {entry.error_code}
              </span>
            )}
            {entry.resource_address && (
              <span className="truncate">{entry.resource_address}</span>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wide text-fg-dim border border-border bg-surface-raised">
            {entry.error_type}
          </span>
          <div className="mt-1 text-xs text-fg-dim tabular-nums">
            {new Date(entry.created_at).toLocaleDateString()}
          </div>
        </div>
      </div>
    </motion.li>
  );
}
