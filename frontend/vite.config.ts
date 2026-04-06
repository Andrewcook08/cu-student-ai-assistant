import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api/chat': {
        target: 'http://localhost:8001',
        ws: true,
      },
      '/ws': {
        target: 'http://localhost:8001',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8000',
      },
    },
  },
})
