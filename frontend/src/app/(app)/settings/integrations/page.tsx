"use client";

import { motion } from "framer-motion";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { CheckCircle2, ExternalLink, Trash2 } from "lucide-react";

import {
  useGitHubInstallations,
  useLinkGitHub,
  useUnlinkGitHub,
} from "@/lib/hooks/useIntegrations";
import { useTeams } from "@/lib/hooks/useTeams";

const GITHUB_APP_SLUG =
  process.env.NEXT_PUBLIC_FIXDOC_GITHUB_APP_SLUG || "fixdoc";

export default function IntegrationsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: teams } = useTeams();
  const team = teams?.[0];
  const teamId = team?.id;

  const { data: installs } = useGitHubInstallations(teamId);
  const link = useLinkGitHub(teamId);
  const unlink = useUnlinkGitHub(teamId);

  /* Handle GitHub install callback — when GitHub redirects back with
     ?installation_id=... we POST it to our backend to bind the install
     to the current team. The `state` param (set on outbound) guards against
     cross-team claim attacks. */
  useEffect(() => {
    const installId = searchParams.get("installation_id");
    const state = searchParams.get("state");
    if (!installId || !teamId) return;
    if (state && state !== teamId) return; // mismatched state, ignore
    link.mutate(Number(installId), {
      onSettled: () => router.replace("/settings/integrations"),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, teamId]);

  const installUrl =
    teamId &&
    `https://github.com/apps/${GITHUB_APP_SLUG}/installations/new?state=${teamId}`;

  return (
    <div className="max-w-2xl space-y-10">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <h1 className="font-display text-2xl font-semibold tracking-tight">
          Integrations
        </h1>
        <p className="mt-1 text-sm text-fg-muted">
          Connect FixDoc to your code host and chat.
        </p>
      </motion.div>

      <section>
        <header className="mb-4">
          <h2 className="font-display text-base font-semibold">GitHub</h2>
          <p className="text-xs text-fg-muted">
            Install the app → add one step to your Terraform workflow → FixDoc
            posts risk analysis on every plan.
          </p>
        </header>

        {(installs ?? []).length === 0 ? (
          <motion.a
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            href={installUrl || "#"}
            target="_blank"
            rel="noreferrer"
            className="group relative overflow-hidden rounded-xl border border-brand/40 bg-gradient-to-br from-brand/10 via-surface to-surface p-5 shadow-glow-soft transition-all hover:shadow-glow hover:border-brand/60"
          >
            <div
              aria-hidden
              className="pointer-events-none absolute -inset-px rounded-xl opacity-50 transition-opacity group-hover:opacity-80"
              style={{
                background:
                  "radial-gradient(circle at top right, rgba(139,92,246,0.18), transparent 55%)",
              }}
            />
            <div className="relative flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <GitHubMark />
                <div>
                  <div className="font-medium text-fg">Connect GitHub</div>
                  <div className="text-xs text-fg-muted">
                    One-click install. Requests: contents:read, pull_requests:write
                  </div>
                </div>
              </div>
              <ExternalLink className="h-4 w-4 text-fg-muted" strokeWidth={2} />
            </div>
          </motion.a>
        ) : (
          <ul className="space-y-3">
            {installs!.map((inst, i) => (
              <motion.li
                key={inst.installation_id}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04, duration: 0.3 }}
                className="rounded-xl border border-border bg-surface p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <GitHubMark />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-fg">
                        <CheckCircle2
                          className="h-3.5 w-3.5 text-accent-emerald"
                          strokeWidth={2.5}
                        />
                        <span className="font-medium text-sm">Installed</span>
                        <span className="text-[11px] font-mono text-fg-dim">
                          #{inst.installation_id}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-fg-muted">
                        {inst.repositories.length} repository/ies
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      if (
                        confirm(
                          "Unlink this GitHub installation from the team? You can re-link later.",
                        )
                      ) {
                        unlink.mutate(inst.installation_id);
                      }
                    }}
                    className="p-1.5 rounded-md text-fg-dim hover:text-accent-rose hover:bg-accent-rose/10"
                    aria-label="Unlink"
                  >
                    <Trash2 className="h-3.5 w-3.5" strokeWidth={2} />
                  </button>
                </div>
                {inst.repositories.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {inst.repositories.slice(0, 6).map((r) => (
                      <span
                        key={r.id}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono text-fg-muted bg-surface-raised border border-border"
                      >
                        {r.full_name}
                      </span>
                    ))}
                    {inst.repositories.length > 6 && (
                      <span className="text-[11px] text-fg-dim">
                        +{inst.repositories.length - 6} more
                      </span>
                    )}
                  </div>
                )}
              </motion.li>
            ))}
          </ul>
        )}

        <div className="mt-6 rounded-lg border border-border-subtle bg-surface/60 p-4 text-xs text-fg-muted">
          <div className="font-medium text-fg mb-1">Next step</div>
          Add this to your Terraform workflow:
          <pre className="mt-2 font-mono text-[11px] text-fg bg-[#0c0c0e] rounded p-3 overflow-x-auto">{`- uses: fixdoc/analyze-action@v1
  with:
    plan: plan.json
    api-key: \${{ secrets.FIXDOC_API_KEY }}`}</pre>
        </div>
      </section>

      <section className="opacity-50">
        <header className="mb-2 flex items-center justify-between">
          <h2 className="font-display text-base font-semibold">Slack</h2>
          <span className="text-[10px] uppercase tracking-wider text-fg-dim font-mono">
            Phase 1
          </span>
        </header>
        <p className="text-xs text-fg-muted">
          Route recurring errors to a team channel. Coming soon.
        </p>
      </section>
    </div>
  );
}

function GitHubMark() {
  return (
    <div className="h-9 w-9 rounded-md bg-[#0d1117] border border-border flex items-center justify-center shrink-0">
      <svg
        viewBox="0 0 24 24"
        className="h-5 w-5 text-fg"
        fill="currentColor"
        aria-hidden
      >
        <path d="M12 .296c-6.627 0-12 5.372-12 12 0 5.302 3.438 9.8 8.205 11.387.6.11.82-.26.82-.577 0-.285-.01-1.04-.015-2.04-3.338.725-4.042-1.61-4.042-1.61-.546-1.385-1.333-1.756-1.333-1.756-1.089-.745.082-.73.082-.73 1.205.085 1.838 1.236 1.838 1.236 1.07 1.835 2.807 1.305 3.492.997.108-.775.418-1.305.762-1.604-2.665-.303-5.467-1.334-5.467-5.932 0-1.31.467-2.38 1.236-3.22-.124-.303-.536-1.524.117-3.176 0 0 1.008-.322 3.3 1.23a11.5 11.5 0 0 1 3-.404c1.02.005 2.047.138 3 .404 2.29-1.552 3.297-1.23 3.297-1.23.656 1.652.244 2.873.12 3.176.77.84 1.235 1.91 1.235 3.22 0 4.61-2.807 5.625-5.48 5.922.43.37.824 1.103.824 2.222 0 1.606-.015 2.896-.015 3.293 0 .32.216.694.825.576C20.565 22.092 24 17.594 24 12.296c0-6.628-5.373-12-12-12"/>
      </svg>
    </div>
  );
}
