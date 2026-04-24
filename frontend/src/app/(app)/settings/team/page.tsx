"use client";

import { motion } from "framer-motion";
import { Users } from "lucide-react";

import { useTeamMembers, useTeams } from "@/lib/hooks/useTeams";

export default function TeamSettingsPage() {
  const { data: teams } = useTeams();
  const team = teams?.[0];
  const { data: members } = useTeamMembers(team?.id);

  return (
    <div className="max-w-3xl space-y-10">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <span className="eyebrow mb-2">
          <span className="pulse-dot" />
          team
        </span>
        <h1 className="font-display text-[2rem] leading-tight">
          {team ? team.name : "Team"}
        </h1>
        {team && (
          <p className="mt-1 font-mono text-[12px] text-fg-muted">
            slug/<span className="text-fg">{team.slug}</span>
          </p>
        )}
      </motion.div>

      <section>
        <header className="mb-4 flex items-center justify-between">
          <span className="eyebrow">
            members · {members?.length ?? 0}
          </span>
          <button
            disabled
            title="Coming in Phase 1"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-surface/60 font-mono text-[12px] text-fg-muted cursor-not-allowed opacity-60"
          >
            <Users className="h-3.5 w-3.5" strokeWidth={2} />
            invite
            <span className="ml-1 px-1 rounded bg-border text-[9px] uppercase tracking-wider">
              phase 1
            </span>
          </button>
        </header>

        <div className="terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">$ fd team members</span>
          </div>
          <ul className="divide-y divide-border-subtle">
            {(members ?? []).map((m, i) => (
              <motion.li
                key={m.user_id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04, duration: 0.3 }}
                className="flex items-center justify-between px-4 py-3"
              >
                <div className="min-w-0 font-mono text-[12px]">
                  <div className="flex items-center gap-2">
                    <span className="text-brand">●</span>
                    <span className="text-fg truncate">
                      user_{m.user_id.slice(0, 8)}
                    </span>
                  </div>
                  <div className="pl-4 mt-0.5 text-[11px] text-term-comment">
                    joined {new Date(m.joined_at).toLocaleDateString()}
                  </div>
                </div>
                <span className="font-mono text-[10px] uppercase tracking-wider text-term-comment px-1.5 py-0.5 rounded border border-border bg-surface">
                  {m.role}
                </span>
              </motion.li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
