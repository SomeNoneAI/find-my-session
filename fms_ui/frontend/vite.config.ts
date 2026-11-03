import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    // The Python server serves this directory verbatim; keep the exact file
    // names its STATIC_FILES mapping expects.
    outDir: "../static",
    emptyOutDir: true,
    assetsDir: "",
    rollupOptions: {
      output: {
        entryFileNames: "app.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (assetInfo) =>
          assetInfo.name && assetInfo.name.endsWith(".css")
            ? "styles.css"
            : "assets/[name]-[hash][extname]",
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.ts"],
    globals: false,
  },
});
