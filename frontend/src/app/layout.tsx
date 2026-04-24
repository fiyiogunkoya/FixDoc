import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { Inter, JetBrains_Mono } from "next/font/google";

import { QueryProvider } from "@/components/providers/QueryProvider";
import "./globals.css";

/* Mirror the marketing site exactly: Inter (ui) + JetBrains Mono (code).
 * Signing in from fixdoc.dev → app.fixdoc.dev should feel like the same
 * typeface system is following the user through the door. */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  weight: ["300", "400", "500", "600", "700", "800", "900"],
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  weight: ["400", "500", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "FixDoc",
  description:
    "Tribal knowledge for infrastructure engineers — team fix database, PR risk analysis, K8s change intelligence.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider
      appearance={{
        baseTheme: dark,
        variables: {
          colorPrimary: "#00ff88",
          colorBackground: "#0a0a0a",
          colorInputBackground: "#111111",
          colorInputText: "#f0f0f0",
          colorText: "#f0f0f0",
          colorTextSecondary: "#888888",
          colorDanger: "#ff4d6d",
          colorSuccess: "#00ff88",
          borderRadius: "0.5rem",
          fontFamily: "var(--font-inter)",
        },
        elements: {
          rootBox: "w-full",
          card: "bg-surface border border-border shadow-card backdrop-blur-sm",
          headerTitle: "font-display tracking-tight-display text-fg",
          headerSubtitle: "text-fg-muted",
          socialButtonsBlockButton:
            "bg-surface-raised border border-border hover:border-border-strong text-fg transition-colors",
          formButtonPrimary:
            "bg-brand hover:bg-brand-muted text-bg font-semibold transition-all duration-150 active:scale-[0.97] shadow-glow-soft hover:shadow-glow",
          footerActionLink: "text-brand hover:text-brand-muted",
          formFieldInput: "bg-surface-raised border-border",
          identityPreview: "bg-surface-raised border-border",
        },
      }}
    >
      <html lang="en" className={`${inter.variable} ${jetbrains.variable} dark`}>
        <body className="min-h-screen bg-bg text-fg antialiased">
          {/* Ambient phosphor halo — fixed, pointer-events-none, layers beneath
              everything. Subtle green+cyan glow that keeps the infrastructure-
              terminal atmosphere constant without fighting data density. */}
          <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 halo-bg" />
          <QueryProvider>{children}</QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
