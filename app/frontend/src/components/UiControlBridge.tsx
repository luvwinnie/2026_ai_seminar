/**
 * WebMCP ブリッジ — チャットAI(MCPツール)からブラウザ画面を直接コントロールする。
 *
 * 1) バックエンドの SSE(/api/ui/events)を購読し、ui_navigate / ui_open_report が
 *    発行した {action:'navigate', path} を受けて React Router で遷移する。
 * 2) ブラウザが WebMCP(navigator.modelContext)に対応していれば、同じ操作を
 *    ページ側ツールとして登録し、ブラウザ内エージェントからも操作可能にする。
 *
 * 安全設計: 遷移のみ(データ変更なし)。path はアプリ内パス(先頭 '/')だけを許可。
 * 操作時は Snackbar で「AIが画面を操作した」ことを利用者へ明示する。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Snackbar from '@mui/material/Snackbar'
import { useColorMode } from '../colorMode'

const ALLOWED_PREFIXES = ['/dashboard', '/alerts', '/reports', '/chat', '/settings/masters', '/analysis', '/digests', '/capa']

function isSafePath(path: unknown): path is string {
  return typeof path === 'string' && ALLOWED_PREFIXES.some((p) => path === p || path.startsWith(p + '/') || path.startsWith(p + '?'))
}

export default function UiControlBridge() {
  const navigate = useNavigate()
  const { mode, toggle } = useColorMode()
  const [message, setMessage] = useState<string | null>(null)
  const navigateRef = useRef(navigate)
  navigateRef.current = navigate
  const themeRef = useRef({ mode, toggle })
  themeRef.current = { mode, toggle }

  useEffect(() => {
    // --- 1) バックエンド SSE 購読(チャットAIからの操作) ---
    const es = new EventSource('/api/ui/events')
    es.addEventListener('ui', (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev.action === 'navigate' && isSafePath(ev.path)) {
          navigateRef.current(ev.path)
          setMessage(`AIアシスタントが画面を操作しました: ${ev.reason ?? ev.path}`)
        } else if (ev.action === 'command') {
          // 画面内アクション: テーマ切替はここで、それ以外は対象ページへイベント配送
          if (ev.name === 'set_theme') {
            const want = ev.params?.mode
            if ((want === 'dark' || want === 'light') && want !== themeRef.current.mode) {
              themeRef.current.toggle()
            }
            setMessage(`AIアシスタントがテーマを${ev.params?.mode === 'dark' ? 'ダーク' : 'ライト'}に切り替えました`)
          } else {
            if (isSafePath(ev.path)) navigateRef.current(ev.path)
            // ページ遷移後にマウント完了を待ってからコマンドを配送
            const delay = isSafePath(ev.path) ? 800 : 0
            window.setTimeout(() => {
              window.dispatchEvent(new CustomEvent('ai-ui-command', { detail: ev }))
            }, delay)
            setMessage(`AIアシスタントが画面を操作しました: ${ev.reason ?? ev.name}`)
          }
        }
      } catch {
        /* 不正なイベントは無視 */
      }
    })

    // --- 2) WebMCP(navigator.modelContext)へのツール登録(対応ブラウザのみ) ---
    const mc = (navigator as unknown as { modelContext?: { registerTool?: (t: object) => unknown } }).modelContext
    if (mc?.registerTool) {
      try {
        mc.registerTool({
          name: 'defectreport-navigate',
          description:
            'DefectReport AI の画面を遷移する。path 例: /dashboard, /reports, /reports/KZ25-0001, /reports?machine=NC旋盤A',
          inputSchema: {
            type: 'object',
            properties: { path: { type: 'string', description: 'アプリ内パス(先頭 /)' } },
            required: ['path'],
          },
          async execute({ path }: { path: string }) {
            if (isSafePath(path)) {
              navigateRef.current(path)
              return { content: [{ type: 'text', text: `moved to ${path}` }] }
            }
            return { content: [{ type: 'text', text: `invalid path: ${path}` }] }
          },
        })
      } catch {
        /* 提案段階のAPIのため、形が違っても本体機能には影響させない */
      }
    }
    return () => es.close()
  }, [])

  return (
    <Snackbar
      open={message !== null}
      autoHideDuration={4000}
      onClose={() => setMessage(null)}
      message={message}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
    />
  )
}
