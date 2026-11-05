import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // In locale /live non esiste e il sito ripiega sull'istantanea in public/data.
  },
  test: { environment: "jsdom" },
});
