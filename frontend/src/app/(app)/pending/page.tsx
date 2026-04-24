"use client";

import { motion } from "framer-motion";
import { CheckCircle2 } from "lucide-react";

import { cn } from "@/lib/cn";
import { usePending } from "@/lib/hooks/usePending";
import { useTeams } from "@/lib/hooks/useTeams";

export default function PendingPage() {
  const { data: teams } = useTeams();
  const teamId = teams?.[0]?.id;
  const { data: entries, isLoading } = usePending(teamId);

  const worthy = (entries ?? []).filter((e) => e.worthiness === "memory_worthy");
  const selfEx = (entries ?? []).filter((e) => e.worthiness === "self_explanatory");

  return (
    <div className="space-y-8">
      <div>
        <span className="eyebrow mb-2">
          <span className="pulse-dot" />
          deferred errors
        </span>
        <h1 className="font-display text-[2rem] leading-tight">
          Pending <span className="phosphor-text">· {(entries ?? []).length}</span>
        </h1>
        <p className="mt-2 font-mono text-[12px] text-fg-muted">
          captured by <span className="text-brand">$ fixdoc watch</span> · awaiting
          resolution
        </p>
      </div>

      {isLoading && (
        <div className="terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">$ fd pending</span>
          </div>
          <div className="term-body text-center">
            <span className="tc">→ scanning …</span>
          </div>
        </div>
      )}

      {!isLoading && worthy.length === 0 && selfEx.length === 0 && (
        <div className="terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">$ fd pending</span>
          </div>
          <div className="term-body text-center py-10">
            <CheckCircle2
              className="mx-auto h-8 w-8 text-brand"
              strokeWidth={1.5}
            />
            <div className="mt-3 text-fg">
              <span className="ts">✓</span>{" "}
              <span className="tw">no pending errors.</span>
            </div>
            <div className="tc mt-1 text-[12px]">all caught up</div>
          </div>
        </div>
      )}

      {worthy.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <span className="eyebrow">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-amber" />
              memory-worthy · {worthy.length}
            </span>
            <span className="font-mono text-[11px] text-fg-dim">
              will promote to fix on next resolve
            </span>
          </div>

          <div className="terminal">
            <div className="term-hdr">
              <span className="t-dot r" />
              <span className="t-dot y" />
              <span className="t-dot g" />
              <span className="t-lbl">$ fd pending --memory-worthy</span>
            </div>
            <ul className="divide-y divide-border-subtle">
              {worthy.map((e, i) => (
                <PendingRow key={e.id} entry={e} delay={i * 0.04} severity="amber" />
              ))}
            </ul>
          </div>
        </section>
      )}

      {selfEx.length > 0 && (
        <section>
          <span className="eyebrow mb-3">
            <span className="h-1.5 w-1.5 rounded-full bg-fg-dim" />
            self-explanatory · {selfEx.length}
          </span>

          <div className="terminal opacity-80">
            <div className="term-hdr">
              <span className="t-dot r" />
              <span className="t-dot y" />
              <span className="t-dot g" />
              <span className="t-lbl">$ fd pending --all --self-explanatory</span>
            </div>
            <ul className="divide-y divide-border-subtle">
              {selfEx.map((e, i) => (
                <PendingRow key={e.id} entry={e} delay={i * 0.02} severity="dim" />
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}

function PendingRow({
  entry,
  delay,
  severity,
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
  severity: "amber" | "dim";
}) {
  const prefixColor =
    severity === "amber" ? "text-accent-amber" : "text-fg-dim";

  return (
    <motion.li
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="row-sweep relative px-5 py-3.5 transition-colors hover:bg-surface/40"
    >
      <div className="flex items-start gap-4 font-mono text-[13px]">
        <span className="text-fg-dim shrink-0">
          [{new Date(entry.created_at).toISOString().slice(0, 10)}]
        </span>
        <span className={cn("shrink-0 font-bold", prefixColor)}>⚠</span>

        <div className="min-w-0 flex-1">
          <div
            className={cn(
              "truncate",
              severity === "dim" ? "text-fg-muted" : "text-fg",
            )}
          >
            {entry.short_message}
          </div>
          <div className="mt-1 flex items-center gap-3 text-[11px] text-term-comment">
            {entry.error_code && (
              <span className="text-term-tag">[{entry.error_code}]</span>
            )}
            {entry.resource_address && <span>{entry.resource_address}</span>}
          </div>
        </div>

        <span className="shrink-0 text-[10px] uppercase tracking-wider text-term-comment">
          {entry.error_type}
        </span>
      </div>
    </motion.li>
  );
}
