import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Бэкенд для разработки. Прокси избавляет от CORS и делает пути относительными,
// поэтому VITE_API_BASE_URL в dev можно оставить пустым.
const DEV_API_TARGET = process.env.VITE_DEV_API_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    strictPort: false,
    // Разрешаем любые Host-заголовки: приложение открывается через туннели
    // (ngrok / cloudflared / localtunnel), домены которых заранее неизвестны.
    allowedHosts: true,
    proxy: {
      '/api': {
        target: DEV_API_TARGET,
        changeOrigin: true,
      },
      '/uploads': {
        target: DEV_API_TARGET,
        changeOrigin: true,
      },
      '/health': {
        target: DEV_API_TARGET,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: true,
    port: 4173,
    allowedHosts: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    globals: false,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
