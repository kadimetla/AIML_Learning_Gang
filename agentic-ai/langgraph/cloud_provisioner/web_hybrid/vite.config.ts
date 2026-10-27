import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: the browser only talks to :5174 (same origin, no CORS). Vite forwards the AG-UI
// endpoint and the inventory to the Python server. In production a reverse proxy does the
// same job, see deploy/nginx.conf.
const AGENT_SERVER = process.env.AGENT_SERVER ?? "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/agent": AGENT_SERVER,
      "/inventory": AGENT_SERVER,
    },
  },
});
