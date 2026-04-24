"use client";

import { useTeams } from "@/lib/hooks/useTeams";
import { ChevronsUpDown } from "lucide-react";

/** Minimal team indicator. Full switcher (dropdown + create) ships in Phase 1;
 * for Phase 0 most users will have exactly one team so a label suffices. */
export function TeamSwitcher() {
  const { data: teams, isLoading } = useTeams();
  const team = teams?.[0];

  if (isLoading) {
    return (
      <div className="h-7 w-36 rounded-md bg-surface-raised/60 animate-pulse" />
    );
  }

  if (!team) {
    return (
      <a
        href="/onboarding"
        className="text-sm text-fg-muted hover:text-fg transition-colors"
      >
        Create team →
      </a>
    );
  }

  return (
    <div className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-md border border-border bg-surface-raised/60 text-sm">
      <span className="h-4 w-4 rounded bg-gradient-to-br from-brand to-accent-cyan" />
      <span className="font-medium text-fg">{team.name}</span>
      <ChevronsUpDown className="h-3 w-3 text-fg-dim" strokeWidth={2} />
    </div>
  );
}
