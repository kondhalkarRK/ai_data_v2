import type { NextConfig } from "next";

/**
 * Browser calls stay same-origin (relative `/api`, `/ready`) via rewrites so local
 * CORS / localhost-vs-127.0.0.1 mismatches do not break the dashboard.
 * The rewrite target is the FastAPI process.
 */
const rewriteTarget =
  process.env.API_REWRITE_TARGET ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

const isProduction = process.env.NODE_ENV === "production";

const scriptSrc = isProduction ? "'self' 'unsafe-inline'" : "'self' 'unsafe-inline' 'unsafe-eval'";

const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src ${scriptSrc}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  // Same-origin in dev (rewrites). Keep absolute API hosts for production/direct mode.
  `connect-src 'self' ${rewriteTarget} http://127.0.0.1:8000 http://localhost:8000`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  typescript: {
    ignoreBuildErrors: false,
  },
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion", "@tanstack/react-query"],
  },

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${rewriteTarget}/api/:path*` },
      { source: "/ready", destination: `${rewriteTarget}/ready` },
      { source: "/health", destination: `${rewriteTarget}/health` },
      { source: "/docs", destination: `${rewriteTarget}/docs` },
      { source: "/openapi.json", destination: `${rewriteTarget}/openapi.json` },
    ];
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
