"use client";

import { motion } from "framer-motion";
import { useUser } from "@clerk/nextjs";
import { Database, Clock, GitPullRequest, Users } from "lucide-react";
import Link from "next/link";

import { StatCard } from "@/components/dashboard/StatCard";
import { useFixes } from "@/lib/hooks/useFixes";
import { usePending } from "@/lib/hooks/usePending";
import { useTeamMembers, useTeams } from "@/lib/hooks/useTeams";

export default function DashboardPage() {
  const { user } = useUser();
  const { data: teams } = useTeams();
  const team = teams?.[0];
  const teamId = team?.id;

  const { data: fixes } = useFixes(teamId, { limit: 8 });
  const { data: pending } = usePending(teamId);
  const { data: members } = useTeamMembers(teamId);

  const totalFixes = fixes?.total ?? 0;
  const pendingCount = (pending ?? []).filter((p) => p.worthiness === "memory_worthy").length;
  const memberCount = members?.length ?? 0;
  const firstName = user?.firstName || user?.username || "engineer";

  return (
    <div className="space-y-10">
      {/* EDITORIAL HERO — `$ whoami` prompt leading into a kinetic greeting.
          This sets the tone for the whole app: you're in a terminal session,
          not a generic SaaS dashboard. */}
      <section className="relative -mx-5 md:-mx-8 px-5 md:px-8 py-10 md:py-12 border-b border-border overflow-hidden">
        {/* Ambient halo + grid — layered beneath everything */}
        <div aria-hidden className="absolute inset-0 halo-bg pointer-events-none" />
        <div aria-hidden className="absolute inset-0 grid-bg opacity-40 pointer-events-none" />

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="relative eyebrow mb-5"
        >
          <span className="pulse-dot" />
          {team ? `team/${team.slug}` : "workspace"}
          <span className="text-fg-dim">·</span>
          <span className="text-fg-dim">online</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.7, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
          className="relative font-display text-[clamp(2.25rem,5vw,3.5rem)] leading-[1.08] max-w-[20ch]"
        >
          <span className="font-mono text-brand text-[0.6em] align-middle mr-3">$</span>
          Welcome back,{" "}
          <span className="phosphor-text">{firstName}</span>
          <span className="cursor" />
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="relative mt-4 text-fg-muted text-[0.9375rem] max-w-xl"
        >
          {totalFixes > 0
            ? `${totalFixes.toLocaleString()} fixes indexed · ${pendingCount} deferred errors waiting. Your team's memory is intact.`
            : "Empty database. Run `fixdoc team push` on any machine that has local fixes to backfill."}
        </motion.p>
      </section>

      {/* STAT GRID — every card is a terminal pane */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <span className="eyebrow">
            <span className="pulse-dot" />
            summary
          </span>
          <span className="font-mono text-[11px] text-fg-dim">live · refreshes on focus</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="fixes"
            command="$ fd count --type=fix"
            value={totalFixes}
            icon={Database}
            tone="phosphor"
            index={0}
          />
          <StatCard
            label="pending errors"
            command="$ fd pending --memory-worthy"
            value={pendingCount}
            icon={Clock}
            tone="amber"
            index={1}
          />
          <StatCard
            label="pr comments"
            command="$ gh api … --this-week"
            value={0}
            unit="this week"
            icon={GitPullRequest}
            tone="cyan"
            index={2}
          />
          <StatCard
            label="members"
            command="$ fd team members"
            value={memberCount}
            icon={Users}
            tone="phosphor"
            index={3}
          />
        </div>
      </section>

      {/* RECENT FIXES — log-line list inside a terminal pane */}
      <motion.section
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="mb-4 flex items-center justify-between">
          <span className="eyebrow">
            <span className="pulse-dot" />
            recent fixes
          </span>
          <Link
            href="/fixes"
            className="font-mono text-[11px] text-fg-muted hover:text-fg transition-colors"
          >
            view all →
          </Link>
        </div>

        <div className="terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">$ fd list --limit=8 --sort=recent</span>
          </div>

          <ul className="divide-y divide-border-subtle">
            {(fixes?.items ?? []).slice(0, 8).map((fix, i) => (
              <motion.li
                key={fix.id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.55 + i * 0.035, duration: 0.35 }}
              >
                <Link
                  href={`/fixes/${fix.id}`}
                  className="row-sweep relative block px-5 py-3.5 font-mono text-[13px] transition-colors hover:bg-surface/40"
                >
                  <div className="flex items-start gap-4">
                    {/* Left rail: timestamp in dim mono, dim brackets */}
                    <span className="text-fg-dim shrink-0">
                      [{new Date(fix.updated_at).toISOString().slice(0, 10)}]
                    </span>
                    <span className="text-brand shrink-0">→</span>
                    <div className="min-w-0 flex-1">
                      <div className="text-fg truncate">{fix.issue}</div>
                      {fix.tags && fix.tags.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1 text-[11px] text-term-tag">
                          {fix.tags.slice(0, 4).map((tag) => (
                            <span key={tag}>#{tag}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <span className="ml-auto text-term-comment uppercase text-[10px] tracking-wider shrink-0">
                      {fix.memory_type}
                    </span>
                  </div>
                </Link>
              </motion.li>
            ))}
            {fixes && fixes.items.length === 0 && (
              <li className="px-5 py-10 text-center font-mono text-[13px] text-fg-muted">
                <span className="tp">$</span> <span className="tw">fixdoc team push</span>
                <div className="mt-1 text-term-comment text-[12px]">
                  no fixes yet — run the above to sync your local database
                </div>
              </li>
            )}
          </ul>
        </div>
      </motion.section>
    </div>
  );
}
