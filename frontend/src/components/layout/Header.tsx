"use client";

import { UserButton } from "@clerk/nextjs";
import { Search, Plus } from "lucide-react";

import { TeamSwitcher } from "./TeamSwitcher";

export function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between gap-4 px-5">
        <div className="flex items-center gap-3 flex-1 max-w-xl">
          <TeamSwitcher />

          {/* Command-palette-style quick search — activates full UI later.
              For Phase 0 this is visual affordance only; /fixes page has real search. */}
          <button
            className="group hidden md:flex items-center gap-2 flex-1 px-3 py-1.5 rounded-md border border-border bg-surface-raised/60 text-fg-muted text-sm transition-colors hover:bg-surface-hover hover:border-border-strong"
            onClick={() => (window.location.href = "/fixes")}
          >
            <Search className="h-3.5 w-3.5" strokeWidth={2} />
            <span className="flex-1 text-left">Search fixes…</span>
            <kbd className="hidden lg:inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-border text-[10px] font-mono text-fg-dim">
              ⌘K
            </kbd>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-brand text-white text-sm font-medium shadow-glow-soft transition-all duration-150 hover:bg-brand/90 active:scale-[0.98]"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            New fix
          </button>
          <UserButton
            appearance={{
              elements: { avatarBox: "h-7 w-7 ring-1 ring-border" },
            }}
          />
        </div>
      </div>
    </header>
  );
}
