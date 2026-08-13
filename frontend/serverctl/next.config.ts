import type { NextConfig } from "next";

// The dashboard is a pure client-side app — every page is "use client", there
// are no server components fetching data, no route handlers and no middleware.
// So it builds to plain static files, which the FastAPI backend serves directly
// from one process. That is why there is no Node runtime in the final image.
//
// Security headers are deliberately NOT set here: `headers()` requires a Next
// server, which a static export does not have, so Next would silently drop
// them. They are set by the backend instead (see backend/agent/main.py), which
// is the only thing actually serving these files.
const nextConfig: NextConfig = {
  output: "export",

  // Emits out/login/index.html rather than out/login.html, so a plain static
  // file server resolves /login without any rewrite rules.
  trailingSlash: true,
};

export default nextConfig;
