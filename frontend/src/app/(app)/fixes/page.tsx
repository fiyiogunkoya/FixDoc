"use client";

import Link from "next/link";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search } from "lucide-react";

import { useFixes } from "@/lib/hooks/useFixes";
import { useTeams } from "@/lib/hooks/useTeams";

export default function FixesPage() {
  const [q, setQ] = useState("");
  const { data: teams } = useTeams();
  const teamId = teams?.[0]?.id;
  const { data, isLoading } = useFixes(teamId, { q: q || undefined, limit: 50 });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Fixes</h1>
        <span className="text-sm text-fg-muted tabular-nums">
          {data?.total ?? 0} total
        </span>
      </div>

      {/* Raycast-style search bar — oversized input, icon-left, no border on
          focus jank; instead we swap the border color. */}
      <div className="relative">
        <Search
          className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-fg-dim pointer-events-none"
          strokeWidth={2}
        />
        <input
          autoFocus
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by issue, resolution, notes…"
          className="w-full rounded-lg border border-border bg-surface pl-10 pr-4 py-3 text-[15px] placeholder-fg-dim outline-none transition-colors focus:border-brand/60 focus:bg-surface-raised"
        />
      </div>

      <div className="rounded-xl border border-border bg-surface">
        {isLoading && (
          <div className="px-5 py-8 text-center text-sm text-fg-muted">
            Loading…
          </div>
        )}
        {!isLoading && data && data.items.length === 0 && (
          <div className="px-5 py-14 text-center">
            <div className="text-sm text-fg-muted">No fixes match that search.</div>
            <div className="mt-2 text-xs text-fg-dim">
              Try <code className="font-mono text-fg">fixdoc team push</code> from your
              terminal to upload local fixes.
            </div>
          </div>
        )}
        <AnimatePresence mode="popLayout">
          <ul className="divide-y divide-border">
            {(data?.items ?? []).map((fix, i) => (
              <motion.li
                key={fix.id}
                layout
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ delay: Math.min(i, 10) * 0.02, duration: 0.3 }}
              >
                <Link
                  href={`/fixes/${fix.id}`}
                  className="row-shimmer relative block px-5 py-4 transition-colors hover:bg-surface-hover/40"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-fg truncate">{fix.issue}</div>
                      <div className="mt-1 text-sm text-fg-muted line-clamp-2">
                        {fix.resolution}
                      </div>
                      {fix.tags && fix.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {fix.tags.map((tag) => (
                            <span
                              key={tag}
                              className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wide text-fg-muted bg-surface-raised border border-border"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="shrink-0 text-right">
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wide border border-border bg-surface-raised text-fg-dim">
                        {fix.memory_type}
                      </span>
                      <div className="mt-1 text-xs text-fg-dim tabular-nums">
                        {new Date(fix.updated_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                </Link>
              </motion.li>
            ))}
          </ul>
        </AnimatePresence>
      </div>
    </div>
  );
}
