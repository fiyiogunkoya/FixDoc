import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { dark } from "@clerk/themes";
import { Bricolage_Grotesque, DM_Sans, JetBrains_Mono } from "next/font/google";

import { QueryProvider } from "@/components/providers/QueryProvider";
import "./globals.css";

/* Fonts match the marketing site (fixdoc-web/index.html) so the transition
   from landing → app feels seamless. */
const bricolage = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});
const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  weight: ["400", "500", "600"],
  display: "swap",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "FixDoc",
  description: "Tribal knowledge for infrastructure engineers — team fix database, PR risk analysis, K8s change intelligence.",
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
          colorPrimary: "#8b5cf6",
          colorBackground: "#0a0a0b",
          colorInputBackground: "#16161a",
          colorInputText: "#ededed",
          colorText: "#ededed",
          colorTextSecondary: "#a8a8ad",
          borderRadius: "0.5rem",
          fontFamily: "var(--font-dm-sans)",
        },
        elements: {
          card: "bg-surface border border-border shadow-deep",
          headerTitle: "font-display",
          formButtonPrimary:
            "bg-brand hover:bg-brand/90 text-white transition-all duration-200 active:scale-[0.98]",
        },
      }}
    >
      <html lang="en" className={`${bricolage.variable} ${dmSans.variable} ${jetbrains.variable} dark`}>
        <body className="min-h-screen bg-bg text-fg antialiased">
          {/* Ambient mesh — fixed, pointer-events-none so it never intercepts clicks.
              Sits behind everything to give the dashboard subtle depth without
              distracting from data density. */}
          <div
            aria-hidden
            className="pointer-events-none fixed inset-0 -z-10 bg-mesh-dark"
          />
          <QueryProvider>{children}</QueryProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
