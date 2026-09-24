import type { NextConfig } from "next";

/**
 * URLs that must not dead-end, mapped onto the dashboard.
 *
 * The first group is what the "consolidate the app into a single dashboard"
 * refactor removed. The second is the post-rename name for goals: there is no
 * /todos *page* (the dashboard card is the UI), but it is the URL anyone
 * reaches for after the rename, so it should not 404 either.
 *
 * Temporary (307) on purpose: nothing guarantees the dashboard stays the only
 * page, so browsers must not cache these forever.
 */
const REDIRECT_TO_DASHBOARD = [
  "/goals",
  "/goals/:path*",
  "/insights",
  "/insights/:path*",
  "/memories",
  "/todos",
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits .next/standalone for the slim production Docker image.
  output: "standalone",
  async redirects() {
    return REDIRECT_TO_DASHBOARD.map((source) => ({
      source,
      destination: "/dashboard",
      permanent: false,
    }));
  },
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
