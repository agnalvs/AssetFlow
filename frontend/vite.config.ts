import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * O proxy encaminha `/api` para o backend do AssetFlow.
 *
 * Consequência importante: o frontend faz requisições sempre para a própria
 * origem, sem CORS e sem host de backend embutido no código. Em produção,
 * quem faz esse encaminhamento é o servidor web — a aplicação não muda.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.ASSETFLOW_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
