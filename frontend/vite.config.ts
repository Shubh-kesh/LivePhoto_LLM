import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    port: 5173,
    // Same-origin M5.8 topology: proxy backend API + launch redemption to FastAPI.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: false },
      '/xbiz/live_photo/l': { target: 'http://localhost:8000', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
