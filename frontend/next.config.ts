import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Pin Turbopack's workspace root to this directory. Without it, Next.js
  // walks up past the nested repo layout to the outer folder where a
  // 0-package stub package-lock.json sits, infers that as the workspace
  // root, and emits a warning every build. See Docs/KNOWN_ISSUES.md
  // § "Repo layout" for the why.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
