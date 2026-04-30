"use client";

import { useTeams } from "@/lib/hooks/useTeams";
import { ChevronsUpDown } from "lucide-react";

/** Minimal team indicator — full switcher arrives in Phase 1. Reads like a
 * terminal path segment: `▮ team/personal`. */
export function TeamSwitcher() {
  const { data: teams, isLoading } = useTeams();
  const team = teams?.[0];

  if (isLoading) {
    return <div className="h-7 w-36 rounded-md bg-surface/60 animate-pulse" />;
  }

  if (!team) {
    return (
      <a
        href="/dashboard"
        className="font-mono text-[13px] text-brand hover:text-brand-muted transition-colors"
      >
        → create team
      </a>
    );
  }

  return (
    <div className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-border bg-surface/60">
      {/* Phosphor bar — echoes the active nav marker in the sidebar */}
      <span className="h-3.5 w-[2px] rounded bg-brand shadow-glow-soft" />
      <span className="font-mono text-[13px] text-fg-muted">
        team/<span className="text-fg font-semibold">{team.slug}</span>
      </span>
      <ChevronsUpDown className="h-3 w-3 text-fg-dim" strokeWidth={2} />
    </div>
  );
}
