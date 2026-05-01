"use client";

import { motion } from "framer-motion";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle2, ExternalLink, Trash2, Link2 } from "lucide-react";

import {
  useGitHubInstallations,
  useLinkGitHub,
  useUnlinkGitHub,
} from "@/lib/hooks/useIntegrations";
import { useTeams } from "@/lib/hooks/useTeams";
import { cn } from "@/lib/cn";

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

  /* GitHub install callback: ?installation_id=… with state=<team_id> from
     our outbound link. Mismatch is dropped silently. */
  useEffect(() => {
    const installId = searchParams.get("installation_id");
    const state = searchParams.get("state");
    if (!installId || !teamId) return;
    if (state && state !== teamId) return;
    link.mutate(Number(installId), {
      onSettled: () => router.replace("/settings/integrations"),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, teamId]);

  const installUrl =
    teamId &&
    `https://github.com/apps/${GITHUB_APP_SLUG}/installations/new?state=${teamId}`;

  // Manual-bind affordance: GitHub doesn't redirect back to the Setup URL
  // when the App is already installed (only on initial install), so the
  // useEffect callback path can leave operators stranded. Keep an explicit
  // "I already installed it" entry that takes the installation_id directly.
  const [showManual, setShowManual] = useState(false);
  const [manualId, setManualId] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualBusy, setManualBusy] = useState(false);

  async function handleManualBind(e: React.FormEvent) {
    e.preventDefault();
    setManualError(null);
    const id = Number(manualId.trim());
    if (!Number.isFinite(id) || id <= 0) {
      setManualError("Installation ID must be a positive number");
      return;
    }
    setManualBusy(true);
    try {
      await link.mutateAsync(id);
      setShowManual(false);
      setManualId("");
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to bind installation";
      setManualError(detail);
    } finally {
      setManualBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-10">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <span className="eyebrow mb-2">
          <span className="pulse-dot" />
          integrations
        </span>
        <h1 className="font-display text-[2rem] leading-tight">Integrations</h1>
        <p className="mt-2 font-mono text-[12px] text-term-comment">
          connect FixDoc to your code host and chat
        </p>
      </motion.div>

      {/* GITHUB — primary integration */}
      <section>
        <header className="mb-4">
          <span className="eyebrow mb-1">github</span>
          <p className="font-mono text-[12px] text-term-comment">
            install app → add one step to your terraform workflow → PR risk
            comments on every plan
          </p>
        </header>

        {(installs ?? []).length === 0 ? (
          <div className="space-y-3">
            <motion.a
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              href={installUrl || "#"}
              target="_blank"
              rel="noreferrer"
              className="cta-sweep group relative block terminal border-brand/40 shadow-glow-soft hover:shadow-glow transition-all"
            >
              <div className="term-hdr !bg-brand/5">
                <span className="t-dot r" />
                <span className="t-dot y" />
                <span className="t-dot g" />
                <span className="t-lbl">$ gh app install fixdoc</span>
              </div>
              <div className="p-5 flex items-center justify-between gap-4 relative">
                <div className="flex items-center gap-4">
                  <GitHubMark />
                  <div>
                    <div className="font-semibold text-fg">Connect GitHub</div>
                    <div className="font-mono text-[12px] text-term-comment mt-0.5">
                      scopes: contents:read · pull_requests:write
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-brand font-mono text-sm">
                  install
                  <ExternalLink className="h-4 w-4" strokeWidth={2} />
                </div>
              </div>
            </motion.a>

            {/* Manual-bind escape hatch — for operators who already installed
                the App via GitHub and didn't get the auto-redirect (which
                only fires on first install, not on Configure). */}
            {!showManual ? (
              <button
                onClick={() => setShowManual(true)}
                className="font-mono text-[12px] text-term-comment hover:text-fg transition-colors"
              >
                already installed? bind manually →
              </button>
            ) : (
              <motion.form
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                onSubmit={handleManualBind}
                className="terminal"
              >
                <div className="term-hdr">
                  <span className="t-dot r" />
                  <span className="t-dot y" />
                  <span className="t-dot g" />
                  <span className="t-lbl">$ fd integrations bind --installation-id</span>
                </div>
                <div className="p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <Link2 className="h-3.5 w-3.5 text-fg-dim shrink-0" strokeWidth={2} />
                    <input
                      type="text"
                      autoFocus
                      value={manualId}
                      onChange={(e) => setManualId(e.target.value.replace(/[^0-9]/g, ""))}
                      placeholder="123456"
                      inputMode="numeric"
                      className="flex-1 bg-transparent outline-none font-mono text-sm text-fg placeholder-fg-dim"
                    />
                    <button
                      type="submit"
                      disabled={!manualId || manualBusy}
                      className={cn(
                        "cta-sweep inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md",
                        "bg-brand text-bg font-mono text-[12px] font-bold",
                        "transition-all duration-150 hover:shadow-glow active:scale-[0.97]",
                        "disabled:opacity-40 disabled:cursor-not-allowed",
                      )}
                    >
                      {manualBusy ? "binding…" : "bind"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowManual(false);
                        setManualError(null);
                        setManualId("");
                      }}
                      className="font-mono text-[11px] text-fg-dim hover:text-fg"
                    >
                      cancel
                    </button>
                  </div>
                  <p className="font-mono text-[11px] text-term-comment leading-relaxed">
                    → find at{" "}
                    <a
                      href="https://github.com/settings/installations"
                      target="_blank"
                      rel="noreferrer"
                      className="text-brand hover:underline"
                    >
                      github.com/settings/installations
                    </a>{" "}
                    → click <span className="text-fg">configure</span> on FixDoc → the
                    URL ends in /<span className="text-brand">&lt;id&gt;</span>
                  </p>
                  {manualError && (
                    <div className="font-mono text-[12px] flex items-start gap-2">
                      <span className="te shrink-0">✗</span>
                      <span className="te">{manualError}</span>
                    </div>
                  )}
                </div>
              </motion.form>
            )}
          </div>
        ) : (
          <div className="terminal">
            <div className="term-hdr">
              <span className="t-dot r" />
              <span className="t-dot y" />
              <span className="t-dot g" />
              <span className="t-lbl">$ gh app list</span>
            </div>
            <ul className="divide-y divide-border-subtle">
              {installs!.map((inst, i) => (
                <motion.li
                  key={inst.installation_id}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.3 }}
                  className="p-5"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <GitHubMark />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 font-mono text-[13px]">
                          <CheckCircle2
                            className="h-3.5 w-3.5 text-brand"
                            strokeWidth={2.5}
                          />
                          <span className="text-fg">installed</span>
                          <span className="text-fg-dim">
                            · id/{inst.installation_id}
                          </span>
                        </div>
                        <div className="mt-1 font-mono text-[11px] text-term-comment">
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
                      className="p-1.5 rounded text-fg-dim hover:text-accent-rose hover:bg-accent-rose/10 transition-colors"
                      aria-label="Unlink"
                    >
                      <Trash2 className="h-3.5 w-3.5" strokeWidth={2} />
                    </button>
                  </div>

                  {inst.repositories.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5 pl-[52px]">
                      {inst.repositories.slice(0, 6).map((r) => (
                        <span
                          key={r.id}
                          className="font-mono text-[11px] text-term-tag"
                        >
                          #{r.full_name}
                        </span>
                      ))}
                      {inst.repositories.length > 6 && (
                        <span className="font-mono text-[11px] text-term-comment">
                          +{inst.repositories.length - 6} more
                        </span>
                      )}
                    </div>
                  )}
                </motion.li>
              ))}
            </ul>
          </div>
        )}

        {/* Workflow snippet — same terminal vibe, copy-pastable */}
        <div className="mt-6 terminal">
          <div className="term-hdr">
            <span className="t-dot r" />
            <span className="t-dot y" />
            <span className="t-dot g" />
            <span className="t-lbl">.github/workflows/terraform.yml</span>
          </div>
          <pre className="term-body overflow-x-auto text-[12px] whitespace-pre">
<span className="tc">{`# Add one step to your existing terraform workflow:`}</span>{`
`}<span className="tw">- uses: fixdoc/analyze-action@v1</span>{`
  `}<span className="to">with:</span>{`
    `}<span className="to">plan: plan.json</span>{`
    `}<span className="to">api-key: </span><span className="ti">{`\$\{{ secrets.FIXDOC_API_KEY \}\}`}</span>
          </pre>
        </div>
      </section>

      {/* SLACK — Phase 1 stub */}
      <section className={cn("opacity-50")}>
        <header className="mb-2 flex items-center gap-3">
          <span className="eyebrow">slack</span>
          <span className="font-mono text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-border bg-surface/60 text-fg-dim">
            phase 1
          </span>
        </header>
        <p className="font-mono text-[12px] text-term-comment">
          → route recurring errors to a team channel · shipping next
        </p>
      </section>
    </div>
  );
}

function GitHubMark() {
  return (
    <div className="h-10 w-10 rounded-md bg-[#0d1117] border border-border flex items-center justify-center shrink-0">
      <svg
        viewBox="0 0 24 24"
        className="h-5 w-5 text-fg"
        fill="currentColor"
        aria-hidden
      >
        <path d="M12 .296c-6.627 0-12 5.372-12 12 0 5.302 3.438 9.8 8.205 11.387.6.11.82-.26.82-.577 0-.285-.01-1.04-.015-2.04-3.338.725-4.042-1.61-4.042-1.61-.546-1.385-1.333-1.756-1.333-1.756-1.089-.745.082-.73.082-.73 1.205.085 1.838 1.236 1.838 1.236 1.07 1.835 2.807 1.305 3.492.997.108-.775.418-1.305.762-1.604-2.665-.303-5.467-1.334-5.467-5.932 0-1.31.467-2.38 1.236-3.22-.124-.303-.536-1.524.117-3.176 0 0 1.008-.322 3.3 1.23a11.5 11.5 0 0 1 3-.404c1.02.005 2.047.138 3 .404 2.29-1.552 3.297-1.23 3.297-1.23.656 1.652.244 2.873.12 3.176.77.84 1.235 1.91 1.235 3.22 0 4.61-2.807 5.625-5.48 5.922.43.37.824 1.103.824 2.222 0 1.606-.015 2.896-.015 3.293 0 .32.216.694.825.576C20.565 22.092 24 17.594 24 12.296c0-6.628-5.373-12-12-12" />
      </svg>
    </div>
  );
}
