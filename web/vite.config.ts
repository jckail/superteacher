import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: 'http://localhost:8080', ws: true, changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      output: { manualChunks: (id) => /node_modules\/(react|react-dom|react-router|@tanstack\/react-query)\//.test(id) ? 'vendor' : undefined },
    },
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    environment: 'jsdom',
    maxWorkers: 2,
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
