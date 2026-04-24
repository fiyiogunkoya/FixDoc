"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy, KeyRound } from "lucide-react";

import { useCreateApiKey } from "@/lib/hooks/useTeams";
import { cn } from "@/lib/cn";

interface Props {
  teamId: string | undefined;
}

export function ApiKeyCreate({ teamId }: Props) {
  const [name, setName] = useState("");
  const [revealed, setRevealed] = useState<{ token: string; name: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const { mutateAsync, isPending } = useCreateApiKey(teamId);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !teamId) return;
    const resp = await mutateAsync(name.trim());
    setRevealed({ token: resp.token, name: resp.name });
    setName("");
  }

  async function copyToken() {
    if (!revealed) return;
    await navigator.clipboard.writeText(revealed.token);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-5">
      {/* Generate form — shell-prompt style input with phosphor submit */}
      <form onSubmit={handleCreate} className="terminal">
        <div className="term-hdr">
          <span className="t-dot r" />
          <span className="t-dot y" />
          <span className="t-dot g" />
          <span className="t-lbl">$ fd keygen</span>
        </div>
        <div className="flex items-center px-4 py-3 gap-3">
          <span className="font-mono text-sm text-brand">$</span>
          <span className="font-mono text-sm text-term-comment">keygen --name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder='"laptop"'
            className="flex-1 bg-transparent outline-none font-mono text-sm text-fg placeholder-fg-dim"
          />
          <button
            type="submit"
            disabled={!name.trim() || isPending || !teamId}
            className={cn(
              "cta-sweep inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md",
              "bg-brand text-bg font-mono text-[12px] font-bold",
              "transition-all duration-150 hover:shadow-glow active:scale-[0.97]",
              "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none",
            )}
          >
            <KeyRound className="h-3.5 w-3.5" strokeWidth={2.5} />
            {isPending ? "generating…" : "generate"}
          </button>
        </div>
      </form>

      {/* Single-reveal moment — phosphor glow, shimmer token, copy-once */}
      <AnimatePresence mode="wait">
        {revealed && (
          <motion.div
            key="reveal"
            initial={{ opacity: 0, y: 16, scale: 0.97, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
            className="relative"
          >
            {/* Ambient phosphor halo behind the card */}
            <div
              aria-hidden
              className="absolute -inset-8 opacity-80 pointer-events-none rounded-[32px]"
              style={{
                background:
                  "radial-gradient(ellipse 60% 60% at 30% 30%, rgba(0,255,136,0.14), transparent 55%), radial-gradient(ellipse 50% 60% at 80% 70%, rgba(0,212,255,0.08), transparent 55%)",
              }}
            />

            <div className="relative terminal border-brand/40 shadow-glow-hard">
              <div className="term-hdr !bg-brand/5">
                <span className="t-dot r" />
                <span className="t-dot y" />
                <span className="t-dot g" />
                <span className="t-lbl">
                  <span className="tp">✓</span>{" "}
                  <span className="ts">key generated — copy now</span>
                </span>
              </div>

              <div className="p-5 space-y-4">
                <div>
                  <div className="flex items-center gap-1.5 eyebrow mb-1">
                    <KeyRound className="h-3 w-3" strokeWidth={2.5} />
                    new api key · {revealed.name}
                  </div>
                  <p className="font-mono text-[12px] text-term-comment">
                    → this is the only time the full token will be shown. copy it
                    somewhere safe.
                  </p>
                </div>

                {/* Token itself — huge, mono, shimmer-animated */}
                <div className="relative rounded-lg border border-brand/30 bg-[#040404] p-4">
                  <div
                    aria-hidden
                    className="absolute inset-0 rounded-lg opacity-50 pointer-events-none"
                    style={{
                      background:
                        "radial-gradient(ellipse at 50% 50%, rgba(0,255,136,0.08), transparent 60%)",
                    }}
                  />
                  <code className="relative font-mono text-[13px] text-fg break-all select-all shimmer-text">
                    {revealed.token}
                  </code>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={copyToken}
                    className={cn(
                      "cta-sweep inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md font-mono text-[12px] font-bold transition-all",
                      copied
                        ? "bg-brand/10 border border-brand/50 text-brand"
                        : "bg-brand text-bg hover:shadow-glow active:scale-[0.97]",
                    )}
                  >
                    {copied ? (
                      <>
                        <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
                        copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5" strokeWidth={2.5} />
                        copy token
                      </>
                    )}
                  </button>
                  <span className="font-mono text-[11px] text-term-comment">
                    hashed on our side · never stored in plaintext
                  </span>
                </div>

                {/* CLI pairing hint — same terminal aesthetic */}
                <div className="rounded-lg border border-border bg-[#040404] p-3 font-mono text-[12px] leading-relaxed">
                  <div className="tc mb-1">→ wire up the CLI:</div>
                  <div>
                    <span className="tp">$</span>{" "}
                    <span className="tw">fixdoc login --token</span>{" "}
                    <span className="ti">{revealed.token.slice(0, 18)}…</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* NEXT LEVEL: fire a phosphor particle burst from the center of the token card
   on reveal — react-canvas-confetti with colors=["#00ff88","#00d4ff"], 700ms,
   low density. Marks the moment without being annoying. */
