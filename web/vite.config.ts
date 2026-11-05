import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In sviluppo le chiamate restano same-origin, come in produzione dietro Caddy.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom" },
});
