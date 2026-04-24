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
  Terminal,
  Plug,
} from "lucide-react";

import { cn } from "@/lib/cn";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/fixes", label: "Fixes", icon: Database },
  { href: "/pending", label: "Pending", icon: Clock },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/settings/team", label: "Team", icon: Users },
  { href: "/settings/integrations", label: "Integrations", icon: Plug },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex md:w-[240px] flex-col border-r border-border bg-surface/60 backdrop-blur-sm">
      {/* Brand mark */}
      <Link
        href="/dashboard"
        className="flex items-center gap-2.5 px-5 py-5 border-b border-border group"
      >
        <div className="relative h-7 w-7 rounded-md bg-brand shadow-glow-soft">
          {/* Inner highlight — subtle 3D lift */}
          <div className="absolute inset-0 rounded-md bg-gradient-to-b from-white/20 to-transparent" />
        </div>
        <span className="font-display text-lg font-semibold tracking-tight">
          FixDoc
        </span>
      </Link>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-0.5">
          {NAV.map((item, i) => {
            const active = pathname === item.href || (item.href !== "/dashboard" && pathname?.startsWith(item.href));
            const Icon = item.icon;
            return (
              <li key={item.href}>
                <motion.div
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                >
                  <Link
                    href={item.href}
                    className={cn(
                      "group relative flex items-center gap-3 px-3 py-2 rounded-md text-sm",
                      "transition-colors duration-150",
                      active
                        ? "bg-surface-hover text-fg"
                        : "text-fg-muted hover:text-fg hover:bg-surface-hover/60",
                    )}
                  >
                    {/* Active marker — thin violet bar on the left */}
                    {active && (
                      <motion.span
                        layoutId="sidebar-active"
                        className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-r bg-brand"
                        transition={{ type: "spring", stiffness: 500, damping: 35 }}
                      />
                    )}
                    <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                    <span>{item.label}</span>
                  </Link>
                </motion.div>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* CLI hint at the bottom — drives the user back to the terminal */}
      <div className="mx-3 mb-4 rounded-lg border border-border bg-surface-raised/60 p-3">
        <div className="flex items-center gap-2 text-xs text-fg-muted mb-2">
          <Terminal className="h-3.5 w-3.5" strokeWidth={1.75} />
          <span>CLI access</span>
        </div>
        <code className="block font-mono text-[11px] text-fg-muted">
          pipx install fixdoc
        </code>
      </div>
    </aside>
  );
}
