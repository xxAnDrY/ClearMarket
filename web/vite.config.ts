import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** In sviluppo /api esegue le stesse Netlify Functions del sito pubblicato. */
function localFunctions(): Plugin {
  return {
    name: "local-netlify-functions",
    configureServer(server) {
      server.middlewares.use("/api", async (req, res, next) => {
        const name = (req.url ?? "").split("?")[0].replace(/^\//, "");
        if (!["chart", "movers"].includes(name)) return next();
        const { default: handler } = await server.ssrLoadModule(`/netlify/functions/${name}.ts`);
        const response: Response = await handler(new Request(`http://local${req.originalUrl}`));
        res.statusCode = response.status;
        res.setHeader("Content-Type", "application/json");
        res.end(await response.text());
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), localFunctions()],
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
