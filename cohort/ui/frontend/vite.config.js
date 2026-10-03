import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Builds into ../static, which cohort/ui/api.py mounts when present. The dev
// server proxies /api to the FastAPI process so `npm run dev` and the built
// bundle behave identically.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    host: '127.0.0.1',
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
