import type { NextConfig } from "next";
// Keep the default output: it works with `next start` in Docker and avoids
// Windows symlink requirements during local consultant workstation builds.
const nextConfig: NextConfig = {};
export default nextConfig;
