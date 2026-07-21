import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/tk-admin/',
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    clearMocks: true,
    include: ['src/__tests__/**/*.spec.ts'],
  },
  server: {
    proxy: {
      '/tk-api': 'http://127.0.0.1:8000',
      '/api/v2': 'http://127.0.0.1:8000',
      '/api/v1': 'http://127.0.0.1:8000',
    },
  },
})
