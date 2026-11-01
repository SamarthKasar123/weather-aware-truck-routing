import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api is proxied to the Django server.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.VITE_API_PROXY ?? "http://127.0.0.1:8000" },
  },
});
