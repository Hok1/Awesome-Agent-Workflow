import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({
  base: "/assets/benchmark/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/aaw_skill_eval/static/benchmark",
    emptyOutDir: true,
    rollupOptions: { output: { manualChunks: { charts: ["recharts"] } } },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:18110",
      "/health": "http://127.0.0.1:18110",
    },
  },
});
