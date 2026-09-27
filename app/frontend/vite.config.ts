import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// フロントエンド(5173)から バックエンド(8000)へ /api と /health をプロキシする。
// これにより開発時も本番(nginx)と同じ相対パス('/api/...')でリクエストできる。
// バックエンドのポートを変えたい場合は環境変数 BACKEND_URL で上書きできる。
// 注: 'localhost' は Node 17+ で IPv6(::1)優先で解決されるため、
// 127.0.0.1 のみに bind する uvicorn に届かず 502 になる。IPv4 を明示する。
const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/health': { target: backend, changeOrigin: true },
    },
  },
})
