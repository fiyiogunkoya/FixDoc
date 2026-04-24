"use client";

import { motion } from "framer-motion";
import { Users } from "lucide-react";

import { useTeamMembers, useTeams } from "@/lib/hooks/useTeams";

export default function TeamSettingsPage() {
  const { data: teams } = useTeams();
  const team = teams?.[0];
  const { data: members } = useTeamMembers(team?.id);

  return (
    <div className="max-w-2xl space-y-10">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h1 className="font-display text-2xl font-semibold tracking-tight">Team</h1>
        {team && (
          <p className="mt-1 text-sm text-fg-muted">
            {team.name} · {team.slug}
          </p>
        )}
      </motion.div>

      <section>
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="font-display text-base font-semibold">Members</h2>
            <p className="text-xs text-fg-muted">
              {members?.length ?? 0}{" "}
              {members?.length === 1 ? "member" : "members"}
            </p>
          </div>
          <button
            disabled
            title="Coming in Phase 1"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border bg-surface-raised text-sm text-fg-muted cursor-not-allowed opacity-60"
          >
            <Users className="h-3.5 w-3.5" strokeWidth={2} />
            Invite
          </button>
        </header>

        <div className="rounded-xl border border-border bg-surface overflow-hidden divide-y divide-border">
          {(members ?? []).map((m, i) => (
            <motion.div
              key={m.user_id}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04, duration: 0.3 }}
              className="flex items-center justify-between px-4 py-3"
            >
              <div className="min-w-0">
                <div className="text-sm text-fg font-mono truncate">{m.user_id.slice(0, 8)}</div>
                <div className="text-[11px] text-fg-dim">
                  joined {new Date(m.joined_at).toLocaleDateString()}
                </div>
              </div>
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wide border border-border bg-surface-raised text-fg-muted">
                {m.role}
              </span>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}
