import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      // The C2 admin dashboard (/admin) talks to components/c2-knowledge-graph/service,
      // `python -m app.admin_ui`, on 127.0.0.1:8765. Proxying avoids CORS and keeps that
      // server local-only, matching how it was designed.
      "/c2-api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/c2-api/, ""),
      },
    },
  },
});
