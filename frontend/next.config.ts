import type { NextConfig } from "next";

const backendUrl = "http://localhost:8000";

/** Static export in production; in development, proxy /api to the local backend. */
const nextConfig: NextConfig =
  process.env.NODE_ENV === "development"
    ? {
        compress: false,
        devIndicators: false,
        rewrites: async () => [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }],
      }
    : { output: "export", images: { unoptimized: true } };

export default nextConfig;
