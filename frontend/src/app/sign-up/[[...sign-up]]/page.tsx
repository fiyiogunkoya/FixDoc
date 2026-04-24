"use client";

import { SignUp } from "@clerk/nextjs";
import { motion } from "framer-motion";

export default function SignUpPage() {
  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-6 grid-bg">
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="mb-10 flex items-center gap-3"
      >
        <div className="h-8 w-8 rounded-md bg-brand shadow-glow" />
        <div className="font-display text-xl font-semibold">FixDoc</div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
      >
        <SignUp />
      </motion.div>
    </div>
  );
}
