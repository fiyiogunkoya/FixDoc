"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Database,
  Clock,
  Settings,
  Users,
  Plug,
  Terminal,
} from "lucide-react";

import { cn } from "@/lib/cn";

const NAV = [
  { href: "/dashboard", label: "dashboard", icon: LayoutDashboard },
  { href: "/fixes", label: "fixes", icon: Database },
  { href: "/pending", label: "pending", icon: Clock },
  { href: "/settings/integrations", label: "integrations", icon: Plug },
  { href: "/settings/team", label: "team", icon: Users },
  { href: "/settings", label: "settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex md:w-[248px] flex-col border-r border-border bg-bg/60 backdrop-blur-sm">
      {/* Brand mark — ties the app to fixdoc.dev */}
      <Link href="/dashboard" className="flex items-center gap-2.5 px-5 py-5 group">
        <span className="relative h-7 w-7 rounded-md bg-brand shadow-glow-soft group-hover:shadow-glow transition-shadow">
          <span className="absolute inset-0 rounded-md bg-gradient-to-b from-white/30 to-transparent" />
        </span>
        <span className="font-heavy tracking-tight-display text-fg text-[17px]">
          FixDoc
        </span>
      </Link>

      {/* Workspace eyebrow — mono, green, with a live-pulse dot so the app
          feels connected rather than static. */}
      <div className="px-5 mt-4 mb-3 flex items-center justify-between">
        <span className="eyebrow">
          <span className="pulse-dot" />
          workspace
        </span>
        <span className="font-mono text-[10px] text-fg-dim">v0.1.0</span>
      </div>

      <nav className="flex-1 px-3">
        <ul className="space-y-0.5">
          {NAV.map((item, i) => {
            const active =
              pathname === item.href ||
              (item.href !== "/dashboard" && pathname?.startsWith(item.href));
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <motion.div
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    delay: i * 0.03,
                    duration: 0.35,
                    ease: [0.16, 1, 0.3, 1],
                  }}
                >
                  <Link
                    href={item.href}
                    className={cn(
                      "group relative flex items-center gap-3 px-3 py-2.5 rounded-md font-mono text-[13px]",
                      "transition-colors duration-150",
                      active
                        ? "bg-surface text-fg"
                        : "text-fg-muted hover:text-fg hover:bg-surface/60",
                    )}
                  >
                    {/* Active marker — phosphor bar with glow, slides via layoutId */}
                    {active && (
                      <motion.span
                        layoutId="sidebar-active"
                        className="absolute left-0 top-1/2 h-5 w-[2px] -translate-y-1/2 rounded-r bg-brand shadow-glow"
                        transition={{ type: "spring", stiffness: 500, damping: 35 }}
                      />
                    )}
                    <Icon
                      className={cn(
                        "h-[15px] w-[15px] shrink-0 transition-colors",
                        active ? "text-brand" : "text-fg-dim group-hover:text-fg-muted",
                      )}
                      strokeWidth={1.75}
                    />
                    <span className="flex-1 lowercase">{item.label}</span>
                    {active && (
                      <span className="font-mono text-[10px] text-brand">▸</span>
                    )}
                  </Link>
                </motion.div>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* CLI hint footer — a real mini terminal pane steering users back to zsh */}
      <div className="mx-3 mb-4 terminal">
        <div className="term-hdr">
          <span className="t-dot r" />
          <span className="t-dot y" />
          <span className="t-dot g" />
          <span className="t-lbl flex items-center gap-1.5">
            <Terminal className="h-3 w-3" strokeWidth={2} />
            zsh
          </span>
        </div>
        <div className="term-body !py-3 !px-3 text-[11px] leading-[1.7]">
          <div>
            <span className="tp">$</span>{" "}
            <span className="tw">pipx install fixdoc</span>
          </div>
          <div className="tc">→ CLI ships first</div>
        </div>
      </div>
    </aside>
  );
}
