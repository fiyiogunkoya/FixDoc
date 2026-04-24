/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion"],
  },
  async rewrites() {
    const apiUrl = process.env.FIXDOC_API_URL || "http://localhost:8000";
    return [
      { source: "/api/proxy/:path*", destination: `${apiUrl}/:path*` },
    ];
  },
};

export default nextConfig;
