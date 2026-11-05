import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// この PC では画面 5210、API 8110 を使う（仕様書の 5173・8000 の読み替え）
const API_TARGET = process.env.API_TARGET ?? 'http://localhost:8110'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5210,
    strictPort: true,
    proxy: {
      '/api': API_TARGET,
      '/health': API_TARGET,
    },
  },
})
