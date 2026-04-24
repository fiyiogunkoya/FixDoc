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
    <div className="max-w-3xl space-y-12">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      >
        <span className="eyebrow mb-2">
          <span className="pulse-dot" />
          configuration
        </span>
        <h1 className="font-display text-[2rem] leading-tight">Settings</h1>
      </motion.div>

      <section>
        <header className="mb-4">
          <span className="eyebrow mb-1">profile</span>
          <p className="font-mono text-[12px] text-term-comment">
            managed by clerk — click the avatar (top right) to edit
          </p>
        </header>

        <div className="terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">$ whoami</span>
          </div>
          <div className="p-5 space-y-2 font-mono text-[13px]">
            <Field k="user" v={user?.fullName || user?.username || "—"} />
            <Field k="email" v={user?.primaryEmailAddress?.emailAddress || "—"} />
            {team && <Field k="team" v={`${team.name} (${team.slug})`} />}
          </div>
        </div>
      </section>

      <section>
        <header className="mb-4">
          <span className="eyebrow mb-1">cli access</span>
          <p className="font-mono text-[12px] text-term-comment">
            generate a team-scoped api key · paste into{" "}
            <span className="text-brand">fixdoc login</span>
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

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-fg-dim uppercase text-[10px] tracking-wider">{k}</span>
      <span className="text-fg">{v}</span>
    </div>
  );
}
