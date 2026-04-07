import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
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
