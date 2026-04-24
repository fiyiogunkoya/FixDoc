"use client";

import { motion } from "framer-motion";
import { Database, Clock, GitPullRequest, Users } from "lucide-react";
import Link from "next/link";

import { StatCard } from "@/components/dashboard/StatCard";
import { useFixes } from "@/lib/hooks/useFixes";
import { usePending } from "@/lib/hooks/usePending";
import { useTeamMembers, useTeams } from "@/lib/hooks/useTeams";

export default function DashboardPage() {
  const { data: teams } = useTeams();
  const team = teams?.[0];
  const teamId = team?.id;

  const { data: fixes } = useFixes(teamId, { limit: 5 });
  const { data: pending } = usePending(teamId);
  const { data: members } = useTeamMembers(teamId);

  const totalFixes = fixes?.total ?? 0;
  const pendingCount = (pending ?? []).filter((p) => p.worthiness === "memory_worthy").length;
  const memberCount = members?.length ?? 0;

  return (
    <div className="space-y-8">
      {/* Header — typography does the heavy lifting */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          {team ? `${team.name}` : "Welcome"}
        </h1>
        <p className="mt-1 text-fg-muted text-sm">
          Tribal knowledge, indexed and searchable.
        </p>
      </motion.div>

      {/* Stat grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Fixes" value={totalFixes} icon={Database} tone="violet" index={0} />
        <StatCard
          label="Pending errors"
          value={pendingCount}
          icon={Clock}
          tone="amber"
          index={1}
        />
        <StatCard label="PR comments" value={0} icon={GitPullRequest} tone="cyan" trend="this week" index={2} />
        <StatCard label="Members" value={memberCount} icon={Users} tone="emerald" index={3} />
      </div>

      {/* Recent fixes */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.45, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-xl border border-border bg-surface"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="font-display text-base font-semibold">Recent fixes</h2>
          <Link
            href="/fixes"
            className="text-xs text-fg-muted hover:text-fg transition-colors"
          >
            View all →
          </Link>
        </div>
        <ul className="divide-y divide-border">
          {(fixes?.items ?? []).slice(0, 5).map((fix, i) => (
            <motion.li
              key={fix.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.5 + i * 0.05, duration: 0.35 }}
            >
              <Link
                href={`/fixes/${fix.id}`}
                className="row-shimmer relative block px-5 py-3.5 transition-colors hover:bg-surface-hover/40"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-fg">{fix.issue}</div>
                    {fix.tags && fix.tags.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {fix.tags.slice(0, 4).map((tag) => (
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
                  <time className="shrink-0 text-xs text-fg-dim tabular-nums">
                    {new Date(fix.updated_at).toLocaleDateString()}
                  </time>
                </div>
              </Link>
            </motion.li>
          ))}
          {fixes && fixes.items.length === 0 && (
            <li className="px-5 py-10 text-center text-sm text-fg-muted">
              No fixes yet. Run{" "}
              <code className="font-mono text-fg">fixdoc team push</code> to sync
              your local database.
            </li>
          )}
        </ul>
      </motion.section>
    </div>
  );
}
