import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // The build prerenders the page against the board API, whose free host takes about a
  // minute to wake. Give that fetch room rather than failing the deploy.
  staticPageGenerationTimeout: 180,
  // next dev only: lets a VS Code forwarded port (<id>-3000.<region>.devtunnels.ms) load
  // the dev page's assets, so the local board can be shared. `**` spans the region label.
  allowedDevOrigins: ["**.devtunnels.ms"],
};

export default nextConfig;
