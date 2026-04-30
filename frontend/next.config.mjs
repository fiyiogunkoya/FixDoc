/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion"],
  },
  // Backend is hit directly from the browser via NEXT_PUBLIC_FIXDOC_API_URL.
  // No proxy rewrite — see frontend/src/lib/api.ts for rationale (TL;DR:
  // Railway service-to-service via public domain runs into Cloudflare
  // hairpin and the backend URL is already public anyway).
};

export default nextConfig;
