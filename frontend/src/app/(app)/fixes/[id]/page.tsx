"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, CheckCircle2, XCircle } from "lucide-react";

import { useFix } from "@/lib/hooks/useFixes";
import { useTeams } from "@/lib/hooks/useTeams";

export default function FixDetailPage() {
  const params = useParams<{ id: string }>();
  const { data: teams } = useTeams();
  const teamId = teams?.[0]?.id;
  const { data: fix, isLoading } = useFix(teamId, params?.id);

  if (isLoading) {
    return <div className="text-sm text-fg-muted">Loading…</div>;
  }
  if (!fix) {
    return (
      <div className="text-sm text-fg-muted">
        Fix not found.{" "}
        <Link href="/fixes" className="text-brand hover:underline">
          Back to list
        </Link>
      </div>
    );
  }

  const appliedRate =
    fix.applied_count > 0
      ? Math.round((fix.success_count / fix.applied_count) * 100)
      : null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-8">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      >
        <Link
          href="/fixes"
          className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-fg transition-colors mb-4"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={2} />
          All fixes
        </Link>

        <h1 className="font-display text-2xl md:text-3xl font-semibold tracking-tight">
          {fix.issue}
        </h1>

        {fix.tags && fix.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {fix.tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono uppercase tracking-wide text-fg-muted bg-surface-raised border border-border"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        <section className="mt-8">
          <h2 className="text-xs font-medium uppercase tracking-wider text-fg-dim mb-3">
            Resolution
          </h2>
          <div className="rounded-xl border border-border bg-surface p-5 font-mono text-sm whitespace-pre-wrap text-fg-muted leading-relaxed">
            {fix.resolution}
          </div>
        </section>

        {fix.error_excerpt && (
          <section className="mt-6">
            <h2 className="text-xs font-medium uppercase tracking-wider text-fg-dim mb-3">
              Error excerpt
            </h2>
            <pre className="rounded-xl border border-border bg-[#0c0c0e] p-4 font-mono text-xs text-fg-muted overflow-x-auto leading-relaxed">
              {fix.error_excerpt}
            </pre>
          </section>
        )}

        {fix.notes && (
          <section className="mt-6">
            <h2 className="text-xs font-medium uppercase tracking-wider text-fg-dim mb-3">
              Notes
            </h2>
            <div className="rounded-xl border border-border bg-surface p-5 text-sm text-fg whitespace-pre-wrap">
              {fix.notes}
            </div>
          </section>
        )}
      </motion.div>

      {/* Metadata rail — sticks above the fold */}
      <motion.aside
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        className="lg:sticky lg:top-20 self-start space-y-4"
      >
        <div className="rounded-xl border border-border bg-surface p-4 space-y-3 text-sm">
          <Meta label="Type" value={fix.memory_type} mono />
          <Meta
            label="Content hash"
            value={fix.content_hash}
            mono
          />
          <Meta
            label="Created"
            value={new Date(fix.created_at).toLocaleString()}
          />
          <Meta
            label="Updated"
            value={new Date(fix.updated_at).toLocaleString()}
          />
          {fix.author && <Meta label="Author" value={fix.author} />}
        </div>

        {fix.applied_count > 0 && (
          <div className="rounded-xl border border-border bg-surface p-4">
            <div className="text-xs font-medium uppercase tracking-wider text-fg-dim mb-3">
              Effectiveness
            </div>
            <div className="flex items-baseline gap-2">
              <span className="font-display text-2xl font-semibold tabular-nums">
                {appliedRate}%
              </span>
              <span className="text-xs text-fg-muted">
                {fix.success_count}/{fix.applied_count} applications
              </span>
            </div>
            <div className="mt-3 space-y-1.5">
              <div className="flex items-center gap-2 text-xs text-fg-muted">
                <CheckCircle2 className="h-3 w-3 text-accent-emerald" strokeWidth={2} />
                <span>Succeeded {fix.success_count}×</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-fg-muted">
                <XCircle className="h-3 w-3 text-accent-rose" strokeWidth={2} />
                <span>Failed {fix.applied_count - fix.success_count}×</span>
              </div>
            </div>
          </div>
        )}
      </motion.aside>
    </div>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wider text-fg-dim">{label}</div>
      <div className={mono ? "mt-0.5 font-mono text-xs text-fg" : "mt-0.5 text-fg"}>
        {value}
      </div>
    </div>
  );
}
