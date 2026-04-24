"use client";

import { motion, useInView, useMotionValue, useTransform, animate } from "framer-motion";
import { type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

interface StatCardProps {
  label: string;
  value: number;
  icon: LucideIcon;
  trend?: string;
  tone?: "violet" | "cyan" | "emerald" | "amber";
  index?: number;
}

const TONES = {
  violet: {
    glow: "shadow-glow-soft",
    accent: "from-brand/30 to-brand/0",
    icon: "text-brand",
  },
  cyan: {
    glow: "",
    accent: "from-accent-cyan/30 to-accent-cyan/0",
    icon: "text-accent-cyan",
  },
  emerald: {
    glow: "",
    accent: "from-accent-emerald/30 to-accent-emerald/0",
    icon: "text-accent-emerald",
  },
  amber: {
    glow: "",
    accent: "from-accent-amber/30 to-accent-amber/0",
    icon: "text-accent-amber",
  },
};

export function StatCard({
  label,
  value,
  icon: Icon,
  trend,
  tone = "violet",
  index = 0,
}: StatCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const inView = useInView(cardRef, { once: true, margin: "-40px" });

  /* Counter animation — spring-based, feels alive vs. a jarring static number. */
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (latest) => Math.round(latest).toLocaleString());
  const [display, setDisplay] = useState("0");

  useEffect(() => {
    if (!inView) return;
    const controls = animate(mv, value, {
      duration: 1.1,
      ease: [0.16, 1, 0.3, 1], // expo out — fast then settling
    });
    const unsub = rounded.on("change", setDisplay);
    return () => {
      controls.stop();
      unsub();
    };
  }, [inView, value, mv, rounded]);

  /* Mouse-tracking 3D tilt — strength kept modest (6deg) because this is a
   * workspace card, not a marketing showcase. Subtle is the move. */
  const handleMouseMove = (e: React.MouseEvent) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    cardRef.current.style.transform = `perspective(1000px) rotateX(${-y * 4}deg) rotateY(${x * 4}deg)`;
  };
  const handleMouseLeave = () => {
    if (cardRef.current) {
      cardRef.current.style.transform = "perspective(1000px) rotateX(0) rotateY(0)";
    }
  };

  const t = TONES[tone];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={inView ? { opacity: 1, y: 0 } : undefined}
      transition={{ delay: index * 0.08, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
    >
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className={cn(
          "group relative overflow-hidden rounded-xl border border-border bg-surface p-5 transition-[box-shadow,border-color] duration-300",
          "hover:border-border-strong",
          t.glow,
        )}
        style={{ transformStyle: "preserve-3d", willChange: "transform" }}
      >
        {/* Ambient accent glow — sits behind text, fades in on hover */}
        <div
          aria-hidden
          className={cn(
            "absolute -top-20 -right-20 h-40 w-40 rounded-full blur-3xl opacity-40 transition-opacity duration-500 group-hover:opacity-80",
            "bg-gradient-to-br",
            t.accent,
          )}
        />

        <div className="relative flex items-start justify-between mb-4">
          <span className="text-xs font-medium uppercase tracking-wider text-fg-dim">
            {label}
          </span>
          <Icon className={cn("h-4 w-4", t.icon)} strokeWidth={1.75} />
        </div>

        <div className="relative flex items-baseline gap-2">
          <span className="font-display text-4xl font-semibold tabular-nums">
            {display}
          </span>
          {trend && (
            <span className="text-xs text-fg-muted">{trend}</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/* NEXT LEVEL: swap the counter to a spring physics animation with overshoot
   for numbers > 100, or render a sparkline behind the value using SVG
   `pathLength` driven by useMotionValue for Linear-style ambient detail. */
