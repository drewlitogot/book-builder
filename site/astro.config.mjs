// The site's origin and base path come from website.yml via tools/website.py (SITE_ORIGIN, SITE_BASE),
// so the repository name is never hardcoded.
import { defineConfig } from "astro/config";
import react from "@astrojs/react";

export default defineConfig({
  site: process.env.SITE_ORIGIN || "http://localhost",
  base: process.env.SITE_BASE || "/",
  trailingSlash: "always",
  build: { format: "directory" },
  integrations: [react()],
  devToolbar: { enabled: false },
});
