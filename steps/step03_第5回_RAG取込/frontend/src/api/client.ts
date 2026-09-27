import axios from 'axios'

// baseURL は空文字。開発時は vite の proxy が、本番は nginx が /api・/health を
// バックエンド(8000)へ転送するため、常に相対パスでリクエストする。
export const client = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
})

/** axios / fetch のエラーから表示用メッセージを取り出す */
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    return err.message
  }
  if (err instanceof Error) return err.message
  return '不明なエラーが発生しました'
}
