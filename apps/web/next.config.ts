import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Azure Container Apps image.
  output: "standalone",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
