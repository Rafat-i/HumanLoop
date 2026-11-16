import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { environment: "jsdom", pool: "forks", maxWorkers: 1, setupFiles: ["./tests/setup.ts"], include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"], restoreMocks: true },
});
