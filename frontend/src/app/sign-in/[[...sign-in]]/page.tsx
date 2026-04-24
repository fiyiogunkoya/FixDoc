"use client";

import { SignIn } from "@clerk/nextjs";
import { motion } from "framer-motion";

export default function SignInPage() {
  return (
    <div className="relative min-h-screen grid-bg">
      {/* Ambient green halo over the grid — pure atmosphere, no affordance */}
      <div aria-hidden className="pointer-events-none fixed inset-0 halo-bg" />

      <div className="relative grid min-h-screen grid-cols-1 lg:grid-cols-2">
        {/* LEFT — editorial sign of life. On mobile this folds above the form. */}
        <aside className="flex flex-col justify-between px-8 py-10 lg:px-14 lg:py-14">
          <motion.a
            href="https://fixdoc.dev"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="inline-flex items-center gap-2.5 no-underline self-start"
          >
            {/* Brand mark — tiny phosphor tile with inner highlight */}
            <span className="relative h-7 w-7 rounded-md bg-brand shadow-glow-soft">
              <span className="absolute inset-0 rounded-md bg-gradient-to-b from-white/30 to-transparent" />
            </span>
            <span className="font-sans font-heavy tracking-tight-display text-fg text-lg">
              FixDoc
            </span>
          </motion.a>

          <div>
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="eyebrow mb-6"
            >
              <span className="pulse-dot" />
              Signing in to the workspace
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.7, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="font-display text-[clamp(2rem,5vw,3.5rem)] leading-[1.08] mb-6 max-w-[14ch]"
            >
              Tribal knowledge, <br />
              <span className="phosphor-text">indexed for</span>{" "}
              <span className="phosphor-text">infrastructure.</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.55 }}
              className="text-fg-muted max-w-md text-[0.9375rem] leading-relaxed"
            >
              Your team's past fixes, surfaced the moment a Terraform plan or
              K8s change puts them back on the critical path.
            </motion.p>

            {/* Terminal echo — the app remembers you */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.75, ease: [0.16, 1, 0.3, 1] }}
              className="terminal mt-10 max-w-md"
            >
              <div className="term-hdr">
                <span className="t-dot r" />
                <span className="t-dot y" />
                <span className="t-dot g" />
                <span className="t-lbl">~/team · fixdoc</span>
              </div>
              <div className="term-body">
                <div>
                  <span className="tp">$</span>{" "}
                  <span className="tw">fixdoc team pull</span>
                </div>
                <div className="tc">→ fetching team/personal …</div>
                <div>
                  <span className="ts">✓</span>{" "}
                  <span className="to">1,361 fixes indexed</span>
                </div>
                <div>
                  <span className="ts">✓</span>{" "}
                  <span className="to">2 recurring errors resolved</span>
                </div>
                <div>
                  <span className="tp">$</span>
                  <span className="cursor" />
                </div>
              </div>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.0, duration: 0.4 }}
            className="text-[11px] font-mono text-fg-dim"
          >
            FIXDOC v0.1.0 · built for SRE + platform teams
          </motion.div>
        </aside>

        {/* RIGHT — Clerk form, centered */}
        <div className="flex items-center justify-center px-6 py-12 lg:px-10 border-l border-border-subtle">
          <motion.div
            initial={{ opacity: 0, y: 16, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          >
            <SignIn />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
