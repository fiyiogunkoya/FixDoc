import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Surface palette — tuned for OLED-black dashboards (Linear/Vercel vibe)
        bg: "#0a0a0b",
        surface: {
          DEFAULT: "#111113",
          raised: "#16161a",
          hover: "#1c1c21",
        },
        border: {
          DEFAULT: "#1f1f24",
          subtle: "#17171b",
          strong: "#2a2a31",
        },
        fg: {
          DEFAULT: "#ededed",
          muted: "#a8a8ad",
          dim: "#6e6e74",
        },
        // Brand — violet primary, cyan secondary, matches fixdoc-web
        brand: {
          DEFAULT: "#8b5cf6",
          muted: "#6d4fd1",
          glow: "rgba(139, 92, 246, 0.35)",
        },
        accent: {
          cyan: "#06b6d4",
          emerald: "#10b981",
          amber: "#f59e0b",
          rose: "#ef4444",
        },
      },
      fontFamily: {
        display: ["var(--font-bricolage)", "ui-sans-serif", "system-ui"],
        sans: ["var(--font-dm-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "SFMono-Regular"],
      },
      boxShadow: {
        // Layered depth stack — 4 shadows for realism (see Stripe/Linear)
        deep:
          "0 1px 2px rgba(0,0,0,0.3), 0 4px 8px rgba(0,0,0,0.25), 0 16px 32px rgba(0,0,0,0.2), 0 32px 64px rgba(0,0,0,0.15)",
        glow: "0 0 40px rgba(139, 92, 246, 0.25)",
        "glow-soft": "0 0 30px rgba(139, 92, 246, 0.15)",
      },
      backgroundImage: {
        // Mesh gradient — ambient, never central
        "mesh-dark":
          "radial-gradient(ellipse 60% 40% at 15% 20%, rgba(139,92,246,0.12) 0%, transparent 60%), radial-gradient(ellipse 50% 50% at 85% 10%, rgba(6,182,212,0.08) 0%, transparent 55%), radial-gradient(ellipse 70% 50% at 50% 100%, rgba(139,92,246,0.06) 0%, transparent 60%)",
        "noise": "url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22200%22 height=%22200%22%3E%3Cfilter id=%22n%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.9%22/%3E%3CfeColorMatrix values=%220 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.03 0%22/%3E%3C/filter%3E%3Crect width=%22200%22 height=%22200%22 filter=%22url(%23n)%22/%3E%3C/svg%3E')",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulse_ring: {
          "0%": { boxShadow: "0 0 0 0 rgba(139, 92, 246, 0.4)" },
          "70%": { boxShadow: "0 0 0 10px rgba(139, 92, 246, 0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(139, 92, 246, 0)" },
        },
      },
      animation: {
        shimmer: "shimmer 3s linear infinite",
        "fade-up": "fade-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) both",
        "pulse-ring": "pulse_ring 2s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
