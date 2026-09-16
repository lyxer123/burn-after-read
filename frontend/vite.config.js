import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev: proxy /api and /dl to the backend so the SPA can call it same-origin.
// Build: outputs to dist/ which the backend serves at "/".
export default defineConfig({
  plugins: [vue()],
  // relative base so the SPA can be served under a sub-path (e.g. /onedl/)
  base: './',
  server: {
    proxy: {
      '/api': 'http://localhost:8777',
      '/dl': 'http://localhost:8777',
    },
  },
  build: {
    outDir: 'dist',
  },
})
