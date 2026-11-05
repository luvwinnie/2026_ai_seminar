import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// この PC では画面 5220、API 8120 を使う（仕様書の 5173・8000 の読み替え）。
// Docker Compose では API_TARGET=http://backend:8000、WEB_PORT=5173、WEB_HOST=0.0.0.0 を渡す
const API_TARGET = process.env.API_TARGET ?? 'http://localhost:8120'
const WEB_PORT = Number(process.env.WEB_PORT ?? 5220)

export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.WEB_HOST ?? 'localhost',
    port: WEB_PORT,
    strictPort: true,
    proxy: {
      '/api': API_TARGET,
      '/health': API_TARGET,
    },
  },
})
