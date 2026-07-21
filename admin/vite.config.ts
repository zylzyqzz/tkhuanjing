import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/tk-admin/',
  server: {
    proxy: {
      '/tk-api': 'http://127.0.0.1:8000',
      '/api/v2': 'http://127.0.0.1:8000',
    },
  },
})
