"use client";

import { motion } from "framer-motion";
import { useUser } from "@clerk/nextjs";

import { ApiKeyCreate } from "@/components/settings/ApiKeyCreate";
import { ApiKeyList } from "@/components/settings/ApiKeyList";
import { useTeams } from "@/lib/hooks/useTeams";

export default function SettingsPage() {
  const { user } = useUser();
  const { data: teams } = useTeams();
  const team = teams?.[0];

  return (
    <div className="max-w-2xl space-y-10">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h1 className="font-display text-2xl font-semibold tracking-tight">Settings</h1>
      </motion.div>

      <section>
        <header className="mb-4">
          <h2 className="font-display text-base font-semibold">Profile</h2>
          <p className="text-xs text-fg-muted">Managed by Clerk — click your avatar to edit.</p>
        </header>
        <div className="rounded-xl border border-border bg-surface p-5 space-y-3">
          <Field label="Name" value={user?.fullName || user?.username || "—"} />
          <Field label="Email" value={user?.primaryEmailAddress?.emailAddress || "—"} />
          {team && <Field label="Team" value={`${team.name} (${team.slug})`} />}
        </div>
      </section>

      <section>
        <header className="mb-4">
          <h2 className="font-display text-base font-semibold">CLI access</h2>
          <p className="text-xs text-fg-muted">
            Generate an API key to connect <code className="font-mono text-fg">fixdoc</code> on your machine.
          </p>
        </header>
        <ApiKeyCreate teamId={team?.id} />
        <div className="mt-6">
          <ApiKeyList teamId={team?.id} />
        </div>
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs font-medium uppercase tracking-wider text-fg-dim">{label}</span>
      <span className="text-sm text-fg">{value}</span>
    </div>
  );
}
