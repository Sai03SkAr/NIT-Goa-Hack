import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  turbopack: { root: __dirname },  // a stray ~/package-lock.json made Next guess the wrong workspace root
  // Same-origin proxy to FastAPI: Safari rejects some cross-origin localhost POSTs ("Load failed").
  async rewrites() {
    return ["/api/:path*", "/files/:path*", "/uploads/:path*", "/mock/:path*"].map((source) => ({
      source, destination: `${BACKEND}${source}`,
    }));
  },
};

export default nextConfig;
