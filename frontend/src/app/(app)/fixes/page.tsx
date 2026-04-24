"use client";

import Link from "next/link";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, X } from "lucide-react";

import { useFixes } from "@/lib/hooks/useFixes";
import { useTeams } from "@/lib/hooks/useTeams";

export default function FixesPage() {
  const [q, setQ] = useState("");
  const { data: teams } = useTeams();
  const teamId = teams?.[0]?.id;
  const { data, isLoading } = useFixes(teamId, { q: q || undefined, limit: 50 });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <span className="eyebrow mb-2">
            <span className="pulse-dot" />
            fix database
          </span>
          <h1 className="font-display text-[2rem] leading-tight">
            Fixes <span className="phosphor-text">· {data?.total ?? 0}</span>
          </h1>
        </div>
      </div>

      {/* Shell-prompt search — this IS a terminal input, not an imitation */}
      <div className="relative terminal">
        <div className="flex items-center px-4 py-3 gap-3">
          <span className="font-mono text-sm text-brand">$</span>
          <Search className="h-4 w-4 text-fg-dim shrink-0" strokeWidth={2} />
          <input
            autoFocus
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search issue, resolution, notes…"
            className="flex-1 bg-transparent outline-none font-mono text-[14px] text-fg placeholder-fg-dim tracking-tight"
          />
          {q && (
            <button
              onClick={() => setQ("")}
              className="text-fg-dim hover:text-fg transition-colors"
              aria-label="Clear"
            >
              <X className="h-3.5 w-3.5" strokeWidth={2} />
            </button>
          )}
          {!q && <span className="cursor" />}
        </div>
      </div>

      {/* Results — rendered as a terminal log */}
      <div className="terminal">
        <div className="term-hdr">
          <span className="t-dot r" />
          <span className="t-dot y" />
          <span className="t-dot g" />
          <span className="t-lbl">
            {q ? `$ fd search "${q}"` : "$ fd list --all"}
          </span>
        </div>

        {isLoading && (
          <div className="px-5 py-10 text-center font-mono text-[13px] text-fg-muted">
            <span className="tc">→ scanning …</span>
          </div>
        )}

        {!isLoading && data && data.items.length === 0 && (
          <div className="px-5 py-16 text-center font-mono text-[13px] space-y-2">
            <div className="text-fg-muted">no matches.</div>
            <div className="text-term-comment text-[12px]">
              try{" "}
              <code className="tw bg-surface px-1.5 py-0.5 rounded">
                fixdoc team push
              </code>{" "}
              from your terminal to upload local fixes
            </div>
          </div>
        )}

        <AnimatePresence mode="popLayout">
          <ul className="divide-y divide-border-subtle">
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
                  className="row-sweep relative block px-5 py-4 transition-colors hover:bg-surface/40"
                >
                  <div className="flex items-start gap-4">
                    {/* ISO timestamp in dim mono — ops-log vibe */}
                    <span className="font-mono text-[12px] text-fg-dim shrink-0 pt-0.5">
                      [{new Date(fix.updated_at).toISOString().slice(0, 10)}]
                    </span>
                    <span className="font-mono text-brand shrink-0 pt-0.5">→</span>

                    <div className="min-w-0 flex-1">
                      <div className="font-sans font-medium text-fg truncate">
                        {fix.issue}
                      </div>
                      <div className="mt-1 font-sans text-sm text-fg-muted line-clamp-2">
                        {fix.resolution}
                      </div>
                      {fix.tags && fix.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1 font-mono text-[11px] text-term-tag">
                          {fix.tags.map((tag) => (
                            <span key={tag}>#{tag}</span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="shrink-0 text-right">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-term-comment">
                        {fix.memory_type}
                      </span>
                    </div>
                  </div>
                </Link>
              </motion.li>
            ))}
          </ul>
        </AnimatePresence>

        {/* Terminal footer prompt — implies more behind the scroll */}
        {data && data.items.length > 0 && (
          <div className="px-5 py-3 border-t border-border-subtle font-mono text-[12px]">
            <span className="tp">$</span>
            <span className="cursor" />
          </div>
        )}
      </div>
    </div>
  );
}
