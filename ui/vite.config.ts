import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Em desenvolvimento a UI corre no Vite e o motor no Python. O proxy evita CORS
// e deixa os componentes a falar com os mesmos caminhos `/api/...` do pacote.
const target = process.env.NOX_API ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: false },
    },
  },
  build: {
    // O Tauri embute `ui/dist`; manter os nomes estáveis ajuda o diff dos binários.
    outDir: "dist",
    emptyOutDir: true,
  },
});
