import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Come il redirect in netlify.toml: anche in locale il sito legge i dati pubblicati.
    proxy: {
      "/live": {
        target: "https://raw.githubusercontent.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/live/, "/xxAnDrY/ClearMarket/data/public"),
      },
    },
  },
  test: { environment: "jsdom" },
});
