"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

import { useCreateTeam } from "@/lib/hooks/useTeams";
import { cn } from "@/lib/cn";

/** Slug-ifies a team name in real-time as the user types. Lowercase, hyphen
 * for spaces, strip non-[a-z0-9-]. Same rules the backend's regex enforces. */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 64);
}

export function CreateTeamForm() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCreateTeam();

  // Auto-derive slug from name until the user manually edits it
  useEffect(() => {
    if (!slugTouched) setSlug(slugify(name));
  }, [name, slugTouched]);

  const canSubmit = name.trim().length > 0 && slug.length >= 2;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    try {
      await create.mutateAsync({ name: name.trim(), slug });
      // useTeams cache invalidates → parent re-renders with the new team
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to create team. Try a different slug.";
      setError(detail);
    }
  }

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="terminal max-w-xl"
    >
      <div className="term-hdr">
        <span className="t-dot r" />
        <span className="t-dot y" />
        <span className="t-dot g" />
        <span className="t-lbl">$ fd team create</span>
      </div>

      <div className="p-5 space-y-4">
        <div>
          <label
            htmlFor="team-name"
            className="block font-mono text-[11px] uppercase tracking-wider text-fg-dim mb-1.5"
          >
            team name
          </label>
          <input
            id="team-name"
            type="text"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Platform"
            className="w-full bg-[#0c0c0c] border border-border rounded-md px-3 py-2 font-sans text-[15px] text-fg placeholder-fg-dim outline-none transition-colors focus:border-brand/60"
          />
        </div>

        <div>
          <label
            htmlFor="team-slug"
            className="block font-mono text-[11px] uppercase tracking-wider text-fg-dim mb-1.5"
          >
            slug
            <span className="ml-2 text-fg-dim normal-case tracking-normal">
              · used in URLs
            </span>
          </label>
          <div className="flex items-center bg-[#0c0c0c] border border-border rounded-md px-3 py-2 transition-colors focus-within:border-brand/60">
            <span className="font-mono text-sm text-fg-dim mr-1">team/</span>
            <input
              id="team-slug"
              type="text"
              value={slug}
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(slugify(e.target.value));
              }}
              placeholder="platform"
              pattern="[a-z0-9-]+"
              className="flex-1 bg-transparent outline-none font-mono text-sm text-fg placeholder-fg-dim"
            />
          </div>
        </div>

        {error && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="font-mono text-[12px] flex items-start gap-2"
          >
            <span className="te shrink-0">✗</span>
            <span className="te">{error}</span>
          </motion.div>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <span className="font-mono text-[11px] text-term-comment">
            you can rename later · slug is permanent
          </span>
          <button
            type="submit"
            disabled={!canSubmit || create.isPending}
            className={cn(
              "cta-sweep inline-flex items-center gap-1.5 px-4 py-2 rounded-md",
              "bg-brand text-bg font-mono text-[12px] font-bold",
              "transition-all duration-150 hover:shadow-glow active:scale-[0.97]",
              "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:shadow-none",
            )}
          >
            {create.isPending ? "creating…" : "create team"}
            <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        </div>
      </div>
    </motion.form>
  );
}
