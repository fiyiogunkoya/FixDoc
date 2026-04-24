"use client";

import { Trash2 } from "lucide-react";
import { motion } from "framer-motion";

import { useApiKeys, useDeleteApiKey } from "@/lib/hooks/useTeams";

export function ApiKeyList({ teamId }: { teamId: string | undefined }) {
  const { data: keys, isLoading } = useApiKeys(teamId);
  const { mutateAsync: del } = useDeleteApiKey(teamId);

  if (isLoading) {
    return (
      <div className="font-mono text-[13px] text-term-comment">→ loading keys …</div>
    );
  }
  if (!keys || keys.length === 0) {
    return (
      <div className="terminal">
        <div className="term-hdr">
          <span className="t-dot r" />
          <span className="t-dot y" />
          <span className="t-dot g" />
          <span className="t-lbl">$ fd keys list</span>
        </div>
        <div className="term-body text-center py-6">
          <span className="tc">no keys yet — generate one above to connect your CLI.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="terminal">
      <div className="term-hdr">
        <span className="t-dot r" />
        <span className="t-dot y" />
        <span className="t-dot g" />
        <span className="t-lbl">$ fd keys list --team</span>
      </div>
      <ul className="divide-y divide-border-subtle">
        {keys.map((key, i) => (
          <motion.li
            key={key.id}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03, duration: 0.3 }}
            className="group row-sweep relative flex items-center justify-between px-4 py-3 transition-colors hover:bg-surface/40"
          >
            <div className="min-w-0 font-mono text-[12px]">
              <div className="flex items-center gap-2">
                <span className="text-brand">●</span>
                <span className="text-fg">{key.name}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-3 text-[11px] text-term-comment pl-4">
                <span>{key.prefix}_••••••••••••</span>
                <span>·</span>
                <span>
                  {key.last_used_at
                    ? `used ${new Date(key.last_used_at).toLocaleDateString()}`
                    : "never used"}
                </span>
              </div>
            </div>
            <button
              onClick={() => {
                if (
                  confirm(
                    `Revoke "${key.name}"? CLI access with this key will stop working immediately.`,
                  )
                ) {
                  del(key.id);
                }
              }}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded text-fg-dim hover:text-accent-rose hover:bg-accent-rose/10"
              aria-label="Revoke key"
            >
              <Trash2 className="h-3.5 w-3.5" strokeWidth={2} />
            </button>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}
