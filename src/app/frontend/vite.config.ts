import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev server proxies /api to the FastAPI backend. In production the built
// dist is served by FastAPI on the same origin, so no proxy is needed.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:28080',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
