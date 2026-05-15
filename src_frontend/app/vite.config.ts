import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";
import { copyFileSync, mkdirSync, readdirSync } from "fs";

function copyDiagramsPlugin(): Plugin {
  const srcDir = resolve(__dirname, "../../docs/architecture");
  const destDir = resolve(__dirname, "dist/diagrams");

  return {
    name: "copy-diagrams",
    writeBundle() {
      mkdirSync(destDir, { recursive: true });
      for (const file of readdirSync(srcDir)) {
        if (file.endsWith(".html")) {
          copyFileSync(resolve(srcDir, file), resolve(destDir, file));
        }
      }
    },
    configureServer(server) {
      server.middlewares.use("/diagrams", (req, res, next) => {
        const filePath = resolve(srcDir, (req.url || "/").replace(/^\//, ""));
        if (filePath.endsWith(".html")) {
          res.setHeader("Content-Type", "text/html");
          const { readFileSync } = require("fs");
          try {
            res.end(readFileSync(filePath));
          } catch {
            next();
          }
        } else {
          next();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), copyDiagramsPlugin()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8080",
        ws: true,
      },
    },
  },
});
