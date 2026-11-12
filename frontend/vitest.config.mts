import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// `@/` mirrors tsconfig.json's `paths`, so tests import modules the way the app does.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
});
