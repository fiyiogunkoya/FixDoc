"use client";

import { Trash2 } from "lucide-react";
import { motion } from "framer-motion";

import { useApiKeys, useDeleteApiKey } from "@/lib/hooks/useTeams";

export function ApiKeyList({ teamId }: { teamId: string | undefined }) {
  const { data: keys, isLoading } = useApiKeys(teamId);
  const { mutateAsync: del } = useDeleteApiKey(teamId);

  if (isLoading) {
    return <div className="text-sm text-fg-muted">Loading…</div>;
  }
  if (!keys || keys.length === 0) {
    return (
      <div className="rounded-lg border border-border-subtle bg-surface/60 px-4 py-8 text-center text-sm text-fg-muted">
        No keys yet. Generate one above to connect your CLI.
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-surface overflow-hidden">
      {keys.map((key, i) => (
        <motion.li
          key={key.id}
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.03, duration: 0.3 }}
          className="group flex items-center justify-between px-4 py-3 transition-colors hover:bg-surface-hover/40"
        >
          <div className="min-w-0">
            <div className="text-sm font-medium text-fg truncate">{key.name}</div>
            <div className="mt-0.5 flex items-center gap-3 text-[11px] font-mono text-fg-dim">
              <span>{key.prefix}••••••••</span>
              <span>
                {key.last_used_at
                  ? `used ${new Date(key.last_used_at).toLocaleDateString()}`
                  : "never used"}
              </span>
            </div>
          </div>
          <button
            onClick={() => {
              if (confirm(`Revoke "${key.name}"? CLI access with this key will stop working immediately.`)) {
                del(key.id);
              }
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md text-fg-dim hover:text-accent-rose hover:bg-accent-rose/10"
            aria-label="Revoke key"
          >
            <Trash2 className="h-3.5 w-3.5" strokeWidth={2} />
          </button>
        </motion.li>
      ))}
    </ul>
  );
}
