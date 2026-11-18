import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const consoleRoot = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = path.resolve(consoleRoot, "../..");

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    fs: { allow: [consoleRoot, repoRoot] },
    proxy: {
      "/v1": { target: "http://127.0.0.1:4010", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globalSetup: ["./src/test/global-setup.ts"],
    setupFiles: ["./src/test/setup.ts"],
    hookTimeout: 60_000,
    testTimeout: 20_000,
  },
});
