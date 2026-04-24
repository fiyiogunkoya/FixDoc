"use client";

import { motion, useInView, useMotionValue, useTransform, animate } from "framer-motion";
import { type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

interface StatCardProps {
  label: string;          // mono lowercase label (e.g. "fixes")
  command: string;        // shell-style subtitle (e.g. "$ fd count --type=fix")
  value: number;
  icon: LucideIcon;
  unit?: string;
  tone?: "phosphor" | "cyan" | "amber";
  index?: number;
}

const TONES = {
  phosphor: {
    num: "phosphor-text phosphor-glow",
    dot: "bg-brand",
    border: "hover:border-brand/40",
    halo: "from-brand/15 to-transparent",
  },
  cyan: {
    num: "phosphor-text",
    dot: "bg-accent-cyan",
    border: "hover:border-accent-cyan/40",
    halo: "from-accent-cyan/15 to-transparent",
  },
  amber: {
    num: "text-accent-amber",
    dot: "bg-accent-amber",
    border: "hover:border-accent-amber/30",
    halo: "from-accent-amber/15 to-transparent",
  },
};

export function StatCard({
  label,
  command,
  value,
  icon: Icon,
  unit,
  tone = "phosphor",
  index = 0,
}: StatCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const inView = useInView(cardRef, { once: true, margin: "-40px" });

  /* Counter — spring out, not linear. Fast arrival then settle. */
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.round(v).toLocaleString());
  const [display, setDisplay] = useState("0");

  useEffect(() => {
    if (!inView) return;
    const controls = animate(mv, value, {
      duration: 1.2,
      ease: [0.16, 1, 0.3, 1],
    });
    const unsub = rounded.on("change", setDisplay);
    return () => {
      controls.stop();
      unsub();
    };
  }, [inView, value, mv, rounded]);

  /* Mouse-tracking 3D tilt — modest (3°) because cards are dense workspace
     affordances, not marketing showpieces. */
  const onMove = (e: React.MouseEvent) => {
    if (!cardRef.current) return;
    const r = cardRef.current.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    cardRef.current.style.transform = `perspective(1000px) rotateX(${-y * 3}deg) rotateY(${x * 3}deg)`;
  };
  const onLeave = () => {
    if (cardRef.current)
      cardRef.current.style.transform = "perspective(1000px) rotateX(0) rotateY(0)";
  };

  const t = TONES[tone];

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, filter: "blur(2px)" }}
      animate={inView ? { opacity: 1, y: 0, filter: "blur(0px)" } : undefined}
      transition={{ delay: index * 0.08, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
    >
      <div
        ref={cardRef}
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        className={cn(
          "group relative terminal transition-[border-color,box-shadow] duration-300",
          t.border,
          "hover:shadow-lift",
        )}
        style={{ transformStyle: "preserve-3d", willChange: "transform" }}
      >
        {/* Ambient corner halo — fades in on hover */}
        <div
          aria-hidden
          className={cn(
            "absolute -top-16 -right-16 h-32 w-32 rounded-full blur-3xl opacity-30 pointer-events-none transition-opacity duration-500 group-hover:opacity-100",
            "bg-gradient-to-br",
            t.halo,
          )}
        />

        {/* Terminal chrome */}
        <div className="term-hdr relative">
          <span className="t-dot r" />
          <span className="t-dot y" />
          <span className="t-dot g" />
          <span className="t-lbl">{command}</span>
          <Icon className="h-3.5 w-3.5 text-fg-dim ml-auto" strokeWidth={1.75} />
        </div>

        {/* Body — number lives in large display weight; label below in mono */}
        <div className="p-5 relative">
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                "font-display text-5xl font-black tabular-nums leading-none",
                t.num,
              )}
            >
              {display}
            </span>
            {unit && (
              <span className="text-xs font-mono text-fg-dim">{unit}</span>
            )}
          </div>

          <div className="mt-2 flex items-center gap-1.5">
            <span className={cn("h-1 w-1 rounded-full", t.dot)} />
            <span className="font-mono text-[11px] text-fg-muted lowercase tracking-wide">
              {label}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* NEXT LEVEL: render a sparkline of the last-7-day count behind the number,
   SVG pathLength driven by useMotionValue so the line draws in-sync with the
   counter's settle — Linear's "Insights" look. */
