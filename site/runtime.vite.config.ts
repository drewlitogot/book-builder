// Builds the standalone game runtime used by the local builder's preview page.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Only the runtime: don't copy the website's public folder (downloads, games, branding) into it.
  publicDir: false,
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "../tools/web/runtime",
    emptyOutDir: true,
    lib: { entry: "src/game/standalone.tsx", formats: ["iife"], name: "BookBuilderGameBundle", fileName: () => "game-runtime.js" },
  },
});
