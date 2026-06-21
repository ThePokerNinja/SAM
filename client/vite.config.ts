import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// S.A.M. client. Boots with VITE_USE_MOCK=1 (default) so the UI + TierController
// are reviewable without any backend. See README.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: {
    globals: true,
    environment: "node",
  },
});
