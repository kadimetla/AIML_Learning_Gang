import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Same dev proxy as web_hybrid: the browser only talks to :5175, Vite forwards to FastAPI.
const AGENT_SERVER = process.env.AGENT_SERVER ?? "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    proxy: {
      "/agent": AGENT_SERVER,
      "/inventory": AGENT_SERVER,
    },
  },
});
