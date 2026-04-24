import type { Config } from "tailwindcss";

/* Design tokens mirror `fixdoc-web/index.html` verbatim. One source of truth
 * across marketing site and app — signing in from the landing page should
 * feel like stepping through the same door, not walking into another product. */
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0a",
        surface: {
          DEFAULT: "#111111",
          raised: "#161616",
          deep: "#0c0c0c",     // terminal inner panes
          hover: "#1c1c1c",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.07)",
          subtle: "rgba(255,255,255,0.04)",
          strong: "rgba(255,255,255,0.12)",
          phosphor: "rgba(0,255,136,0.2)", // green-tinged border on hover
        },
        fg: {
          DEFAULT: "#f0f0f0",     // tx-1 — primary text
          muted: "#888888",       // tx-2 — secondary
          dim: "#444444",         // tx-3 — tertiary / timestamps
        },
        // Terminal phosphor palette
        brand: {
          DEFAULT: "#00ff88",
          muted: "#00cc6e",
          glow: "rgba(0, 255, 136, 0.35)",
        },
        accent: {
          cyan: "#00d4ff",
          amber: "#f59e0b",
          rose: "#ff4d6d",        // red (terminal-error)
          emerald: "#00ff88",     // alias, for older component imports
        },
        // Syntax hint colors used inside terminal panes
        term: {
          prompt: "#00ff88",      // tp
          comment: "#444444",     // tc
          output: "#888888",      // to
          error: "#ff4d6d",       // te
          success: "#00ff88",     // ts
          info: "#00d4ff",        // ti
          tag: "#f59e0b",         // tt
          write: "#f0f0f0",       // tw
        },
      },
      fontFamily: {
        // Inter for UI (not Bricolage) — matches marketing site
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
        display: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "SFMono-Regular"],
      },
      fontWeight: {
        // Expose the full Inter weight range used in the marketing site
        heavy: "800",
        black: "900",
      },
      letterSpacing: {
        "tightest": "-0.03em",
        "tight-display": "-0.02em",
      },
      boxShadow: {
        // Four-layer stack — copied from marketing --shadow-card
        card:
          "0 1px 2px rgba(0,0,0,0.15), 0 4px 8px rgba(0,0,0,0.12), 0 16px 32px rgba(0,0,0,0.1), 0 32px 64px rgba(0,0,0,0.08)",
        lift:
          "0 1px 2px rgba(0,0,0,0.3), 0 8px 24px rgba(0,0,0,0.4), 0 32px 64px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.03)",
        glow: "0 4px 16px rgba(0,255,136,0.3)",
        "glow-soft": "0 0 24px rgba(0,255,136,0.15)",
        "glow-hard": "0 0 60px rgba(0,255,136,0.45), 0 0 16px rgba(0,255,136,0.25)",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(24px)", filter: "blur(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)", filter: "blur(0)" },
        },
        pulse_dot: {
          "0%,100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.4", transform: "scale(0.7)" },
        },
        blink: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        sweep: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        floatY: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        scanline: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
      },
      animation: {
        "fade-up": "fadeUp 0.7s cubic-bezier(0.16,1,0.3,1) both",
        "pulse-dot": "pulse_dot 2s ease infinite",
        blink: "blink 1s step-end infinite",
        shimmer: "shimmer 3s linear infinite",
        sweep: "sweep 0.4s ease forwards",
        "float-y": "floatY 4s ease-in-out infinite",
        scanline: "scanline 6s linear infinite",
      },
      backgroundImage: {
        "phosphor-gradient":
          "linear-gradient(135deg, #00ff88 0%, #00d4ff 100%)",
        "hero-halo":
          "radial-gradient(ellipse 60% 50% at 30% 20%, rgba(0,255,136,0.08) 0%, transparent 60%), radial-gradient(ellipse 50% 60% at 80% 0%, rgba(0,212,255,0.06) 0%, transparent 60%)",
        grid:
          "linear-gradient(to right, rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.025) 1px, transparent 1px)",
      },
      backgroundSize: {
        grid: "32px 32px",
      },
    },
  },
  plugins: [],
};

export default config;
