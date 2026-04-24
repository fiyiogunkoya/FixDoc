"use client";

import { SignIn } from "@clerk/nextjs";
import { motion } from "framer-motion";

export default function SignInPage() {
  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-6 grid-bg">
      {/* Brand mark — small, keyboard-first energy */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="mb-10 flex items-center gap-3"
      >
        <div className="h-8 w-8 rounded-md bg-brand shadow-glow" />
        <div className="font-display text-xl font-semibold">FixDoc</div>
      </motion.div>

      {/* The Clerk card — glassy, lifted, never flat */}
      <motion.div
        initial={{ opacity: 0, y: 16, filter: "blur(6px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
      >
        <SignIn />
      </motion.div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 0.4 }}
        className="mt-8 text-sm text-fg-dim"
      >
        Tribal knowledge for infrastructure engineers.
      </motion.p>
    </div>
  );
}
