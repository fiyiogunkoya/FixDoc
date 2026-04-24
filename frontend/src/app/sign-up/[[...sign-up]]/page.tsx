"use client";

import { SignUp } from "@clerk/nextjs";
import { motion } from "framer-motion";

export default function SignUpPage() {
  return (
    <div className="relative min-h-screen grid-bg">
      <div aria-hidden className="pointer-events-none fixed inset-0 halo-bg" />

      <div className="relative grid min-h-screen grid-cols-1 lg:grid-cols-2">
        <aside className="flex flex-col justify-between px-8 py-10 lg:px-14 lg:py-14">
          <motion.a
            href="https://fixdoc.dev"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="inline-flex items-center gap-2.5 no-underline self-start"
          >
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
              transition={{ duration: 0.5, delay: 0.2 }}
              className="eyebrow mb-6"
            >
              <span className="pulse-dot" />
              New workspace
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.7, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="font-display text-[clamp(2rem,5vw,3.5rem)] leading-[1.08] mb-6 max-w-[14ch]"
            >
              Three minutes to{" "}
              <span className="phosphor-text">first fix.</span>
            </motion.h1>

            <motion.ol
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.55 }}
              className="space-y-3 text-fg-muted max-w-md"
            >
              {[
                ["01", "Create your account"],
                ["02", "Generate a CLI token"],
                ["03", "fixdoc team push — your fixes are live for the team"],
              ].map(([n, t]) => (
                <li key={n} className="flex items-start gap-3">
                  <span className="font-mono text-xs text-brand pt-[3px]">{n}</span>
                  <span className="text-[0.9375rem]">{t}</span>
                </li>
              ))}
            </motion.ol>
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

        <div className="flex items-center justify-center px-6 py-12 lg:px-10 border-l border-border-subtle">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          >
            <SignUp />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
