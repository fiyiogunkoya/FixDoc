"use client";

import { UserButton } from "@clerk/nextjs";
import { Search, Plus } from "lucide-react";
import { useRouter } from "next/navigation";

import { TeamSwitcher } from "./TeamSwitcher";

export function Header() {
  const router = useRouter();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/80 backdrop-blur-md">
      <div className="flex h-14 items-center justify-between gap-4 px-5">
        <div className="flex items-center gap-3 flex-1 max-w-2xl">
          <TeamSwitcher />

          {/* Shell-prompt search — looks like a terminal rather than a chatbot
              textbox. Press ⌘K to open fuzzy search. `/fixes` is the Phase 0
              page; global command palette ships in Phase 1. */}
          <button
            onClick={() => router.push("/fixes")}
            className="group hidden md:flex items-center gap-2 flex-1 max-w-[520px] px-3 py-1.5 rounded-md border border-border bg-surface/60 text-fg-muted transition-colors hover:border-border-strong hover:text-fg"
          >
            <span className="font-mono text-xs text-brand">$</span>
            <Search className="h-3.5 w-3.5 text-fg-dim" strokeWidth={2} />
            <span className="font-mono text-[13px] flex-1 text-left tracking-tight">
              search fixes…
            </span>
            <kbd className="hidden lg:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-border text-[10px] font-mono text-fg-dim">
              ⌘K
            </kbd>
          </button>
        </div>

        <div className="flex items-center gap-2">
          {/* Primary CTA — phosphor fill, sweep on hover, spring press */}
          <button
            onClick={() => router.push("/fixes")}
            className="cta-sweep hidden md:inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-brand text-bg font-mono text-[12px] font-bold transition-all duration-150 hover:shadow-glow active:scale-[0.97]"
          >
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            new fix
          </button>

          <UserButton
            appearance={{
              elements: {
                avatarBox: "h-7 w-7 ring-1 ring-border hover:ring-brand/60 transition-all",
              },
            }}
          />
        </div>
      </div>
    </header>
  );
}
