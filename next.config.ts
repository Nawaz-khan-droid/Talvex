import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        // Proxy all /api/* requests to the FastAPI backend in Docker.
        // This eliminates CORS issues and simplifies container networking.
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
