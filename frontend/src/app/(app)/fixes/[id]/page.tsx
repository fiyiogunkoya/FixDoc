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
    return (
      <div className="font-mono text-sm text-fg-muted">
        <span className="tc">→ loading fix …</span>
      </div>
    );
  }
  if (!fix) {
    return (
      <div className="font-mono text-sm space-y-2">
        <div className="te">error: fix not found</div>
        <Link href="/fixes" className="text-brand hover:underline text-xs">
          ← back to list
        </Link>
      </div>
    );
  }

  const appliedRate =
    fix.applied_count > 0
      ? Math.round((fix.success_count / fix.applied_count) * 100)
      : null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-10">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <Link
          href="/fixes"
          className="inline-flex items-center gap-1.5 font-mono text-xs text-fg-muted hover:text-fg transition-colors mb-5"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={2} />
          all fixes
        </Link>

        <span className="eyebrow mb-3">
          <span className="pulse-dot" />
          {fix.memory_type}
          <span className="text-fg-dim">·</span>
          <span className="text-fg-dim font-mono normal-case">
            fd-{fix.content_hash.slice(0, 8)}
          </span>
        </span>

        <h1 className="font-display text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-tight-display">
          {fix.issue}
        </h1>

        {fix.tags && fix.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 font-mono text-[12px]">
            {fix.tags.map((tag) => (
              <span key={tag} className="text-term-tag">
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* RESOLUTION — terminal pane, mono, output-styled */}
        <section className="mt-8">
          <div className="eyebrow mb-3">resolution</div>
          <div className="terminal">
            <div className="term-hdr">
              <span className="t-dot r" />
              <span className="t-dot y" />
              <span className="t-dot g" />
              <span className="t-lbl">$ fd show {fix.content_hash.slice(0, 8)} --resolution</span>
            </div>
            <div className="term-body whitespace-pre-wrap">
              <span className="to">{fix.resolution}</span>
            </div>
          </div>
        </section>

        {fix.error_excerpt && (
          <section className="mt-6">
            <div className="eyebrow mb-3">error excerpt</div>
            <div className="terminal">
              <div className="term-hdr">
                <span className="t-dot r" />
                <span className="t-dot y" />
                <span className="t-dot g" />
                <span className="t-lbl">captured output</span>
              </div>
              <pre className="term-body overflow-x-auto whitespace-pre">
                <span className="te">{fix.error_excerpt}</span>
              </pre>
            </div>
          </section>
        )}

        {fix.notes && (
          <section className="mt-6">
            <div className="eyebrow mb-3">notes</div>
            <div className="rounded-xl border border-border bg-surface/60 p-5 text-[14px] leading-relaxed whitespace-pre-wrap">
              {fix.notes}
            </div>
          </section>
        )}
      </motion.div>

      {/* METADATA RAIL — sticky, terse, mono */}
      <motion.aside
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        className="lg:sticky lg:top-20 self-start space-y-4"
      >
        <div className="terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">metadata</span>
          </div>
          <div className="p-4 space-y-3 font-mono text-[12px]">
            <Meta k="type" v={fix.memory_type} />
            <Meta k="hash" v={fix.content_hash} />
            <Meta k="created" v={new Date(fix.created_at).toLocaleString()} dim />
            <Meta k="updated" v={new Date(fix.updated_at).toLocaleString()} dim />
            {fix.author && <Meta k="author" v={fix.author} />}
          </div>
        </div>

        {fix.applied_count > 0 && (
          <div className="terminal">
            <div className="term-hdr">
              <span className="t-dot r" />
              <span className="t-dot y" />
              <span className="t-dot g" />
              <span className="t-lbl">effectiveness</span>
            </div>
            <div className="p-4">
              <div className="flex items-baseline gap-2">
                <span className="font-display text-4xl font-black phosphor-text phosphor-glow tabular-nums leading-none">
                  {appliedRate}%
                </span>
                <span className="font-mono text-[11px] text-fg-muted">
                  {fix.success_count}/{fix.applied_count} applied
                </span>
              </div>
              <div className="mt-3 space-y-1.5 font-mono text-[11px]">
                <div className="flex items-center gap-2 text-fg-muted">
                  <CheckCircle2 className="h-3 w-3 text-term-success" strokeWidth={2} />
                  succeeded {fix.success_count}×
                </div>
                <div className="flex items-center gap-2 text-fg-muted">
                  <XCircle className="h-3 w-3 text-term-error" strokeWidth={2} />
                  failed {fix.applied_count - fix.success_count}×
                </div>
              </div>
            </div>
          </div>
        )}
      </motion.aside>
    </div>
  );
}

function Meta({ k, v, dim }: { k: string; v: string; dim?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-fg-dim uppercase text-[10px] tracking-wider">{k}</span>
      <span className={dim ? "text-fg-muted truncate" : "text-fg truncate"}>{v}</span>
    </div>
  );
}
