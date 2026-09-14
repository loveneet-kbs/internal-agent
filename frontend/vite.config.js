import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Fail if the port is taken rather than silently moving to 5181. A silent
    // fallback means the browser is pointed at a stale server and the app looks
    // broken for no visible reason.
    strictPort: true,
    // Bind dual-stack. Vite's default binds IPv6 only on this machine, so anything
    // that resolves "localhost" to 127.0.0.1 - some browsers, curl, ngrok - gets
    // ECONNREFUSED no matter which port is used. "::" listens on both families.
    host: "::",
    // Vite blocks requests whose Host header it does not recognise. Allowing the
    // ngrok domains lets a tunnel reach the dev server for a demo; the leading dot
    // matches any subdomain, since a free ngrok URL changes on every restart.
    allowedHosts: [".ngrok-free.app", ".ngrok.app", ".ngrok.io"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true
      }
    }
  }
});
