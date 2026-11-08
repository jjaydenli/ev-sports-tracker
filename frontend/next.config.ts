import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // The build prerenders the page against the board API, whose free host takes about a
  // minute to wake. Give that fetch room rather than failing the deploy.
  staticPageGenerationTimeout: 180,
};

export default nextConfig;
