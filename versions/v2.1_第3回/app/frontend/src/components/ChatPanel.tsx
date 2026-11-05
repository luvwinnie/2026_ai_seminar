import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useTheme } from '@mui/material/styles'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import { getChatSession, streamChat, toApiError, type ChatTool } from '../api'
import MarkdownMessage from './MarkdownMessage'

// チャットの本体（05_UI設計書.md S3）。第3回は /chat のページだけで使う（AI パネルは後の回）

const EXAMPLES = ['KZ25-0043 の内容を教えて', '表面キズは何件？', '汎用フライスのバリ残りは何件？これまでの対策は？']
const TOOL_PREFIX = 'defect-reports_'

interface Turn {
  role: 'user' | 'assistant'
  content: string
  tools: ChatTool[]
  thinking: string
}

function ToolLine({ tool }: { tool: ChatTool }) {
  const icon =
    tool.status === 'completed' ? (
      <CheckCircleIcon fontSize="small" color="success" />
    ) : tool.status === 'error' ? (
      <ErrorIcon fontSize="small" color="error" />
    ) : tool.status === 'running' ? (
      <CircularProgress size={14} />
    ) : (
      <HourglassEmptyIcon fontSize="small" color="disabled" />
    )
  const label = { pending: '待機中', running: '実行中', completed: '完了', error: '失敗' }[tool.status]
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }} data-testid="tool-line">
      {icon}
      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
        {tool.name.replace(TOOL_PREFIX, '')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {label}
        {tool.title ? ` · ${tool.title}` : ''}
      </Typography>
    </Stack>
  )
}

function Thinking({ text, streaming }: { text: string; streaming: boolean }) {
  const [open, setOpen] = useState(false)
  const lastLine = text.trim().split('\n').pop() ?? ''
  return (
    <Box data-testid="thinking">
      <Button size="small" color="inherit" onClick={() => setOpen(!open)} sx={{ px: 0, color: 'text.secondary' }}>
        {open ? '▾' : '▸'} 考えています…（{open ? 'たたむ' : '開く'}）
      </Button>
      {/* 本文が届く前は最後の1行を見せる */}
      {!open && streaming && (
        <Typography variant="body2" color="text.secondary" noWrap>
          {lastLine}
        </Typography>
      )}
      <Collapse in={open}>
        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>
          {text}
        </Typography>
      </Collapse>
    </Box>
  )
}

interface ChatPanelProps {
  sessionId: number | null
  onSessionCreated: (sessionId: number) => void
  onTurnFinished: () => void
}

export default function ChatPanel({ sessionId, onSessionCreated, onTurnFinished }: ChatPanelProps) {
  const theme = useTheme()
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // この部品の送信で作った会話。選び直したのではないので、DB から読み直さない（届いた理由や逐次表示を消さない）
  const ownSession = useRef<number | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  // 会話を選んだら、保存した発言（道具の記録と思考も）を戻す
  useEffect(() => {
    if (sessionId === ownSession.current) return
    ownSession.current = null
    setError(null)
    if (sessionId === null) {
      setTurns([])
      return
    }
    const controller = new AbortController()
    setLoading(true)
    getChatSession(sessionId, controller.signal)
      .then((detail) =>
        setTurns(
          detail.messages.map((m) => ({
            role: m.role,
            content: m.content,
            tools: m.tools ?? [],
            thinking: m.thinking ?? '',
          })),
        ),
      )
      .catch((e) => {
        if (!controller.signal.aborted) setError(toApiError(e).message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [sessionId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [turns])

  // 最後の発言（受信中の回答）を書き換える
  const updateLast = (change: (turn: Turn) => Turn) =>
    setTurns((prev) => [...prev.slice(0, -1), change(prev[prev.length - 1])])

  const send = async (text: string) => {
    const message = text.trim()
    if (!message || sending) return
    setInput('')
    setError(null)
    setSending(true)
    setTurns((prev) => [
      ...prev,
      { role: 'user', content: message, tools: [], thinking: '' },
      { role: 'assistant', content: '', tools: [], thinking: '' },
    ])
    // 失敗の理由（コールバックの中で書くので、変数ではなく入れ物に持つ）
    const result: { failed: string | null } = { failed: null }
    try {
      await streamChat(message, sessionId, (event) => {
        if (event.event === 'session') {
          if (event.data.id !== sessionId) {
            ownSession.current = event.data.id
            onSessionCreated(event.data.id)
          }
        } else if (event.event === 'thinking') {
          updateLast((t) => ({ ...t, thinking: t.thinking + event.data.text }))
        } else if (event.event === 'token') {
          updateLast((t) => ({ ...t, content: t.content + event.data.text }))
        } else if (event.event === 'tool') {
          const tool = event.data
          updateLast((t) => ({ ...t, tools: [...t.tools.filter((x) => x.name !== tool.name), tool] }))
        } else if (event.event === 'error') {
          result.failed = event.data.detail
        }
      })
    } catch (e) {
      result.failed = toApiError(e).message
    }
    if (result.failed) {
      setError(result.failed)
      // 何も届かなかった回答の枠は消す（届いた分は出したままにする）
      setTurns((prev) => {
        const last = prev[prev.length - 1]
        return last.content || last.tools.length || last.thinking ? prev : prev.slice(0, -1)
      })
    }
    setSending(false)
    onTurnFinished()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    // Enter で送る、Shift+Enter で改行。日本語の変換を確定する Enter では送らない
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(input)
    }
  }

  return (
    <Stack sx={{ height: '100%', minHeight: 0 }}>
      <Box sx={{ flex: 1, overflowY: 'auto', pr: 1 }} data-testid="chat-messages">
        {loading && <CircularProgress size={20} />}
        {!loading && turns.length === 0 && (
          <Stack spacing={2} sx={{ py: 6, alignItems: 'center' }} data-testid="chat-empty">
            <Typography color="text.secondary">質問を入力してください</Typography>
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', justifyContent: 'center', rowGap: 1 }}>
              {EXAMPLES.map((example) => (
                <Chip key={example} label={example} variant="outlined" onClick={() => void send(example)} />
              ))}
            </Stack>
          </Stack>
        )}
        {turns.map((turn, i) => {
          const streaming = sending && i === turns.length - 1
          return turn.role === 'user' ? (
            <Box key={i} sx={{ my: 1.5 }} data-testid="chat-user">
              <Typography variant="caption" color="text.secondary">
                あなた
              </Typography>
              <Typography sx={{ whiteSpace: 'pre-wrap' }}>{turn.content}</Typography>
            </Box>
          ) : (
            <Box
              key={i}
              data-testid="chat-assistant"
              sx={{ my: 1.5, p: 1.5, border: `1px solid ${theme.palette.divider}`, borderRadius: 1, bgcolor: theme.palette.app.paper }}
            >
              <Typography variant="caption" color="text.secondary">
                AI
              </Typography>
              {turn.tools.map((tool) => (
                <ToolLine key={tool.name} tool={tool} />
              ))}
              {turn.thinking && <Thinking text={turn.thinking} streaming={streaming && !turn.content} />}
              {turn.content ? (
                <MarkdownMessage content={turn.content} />
              ) : (
                streaming && <CircularProgress size={16} sx={{ mt: 1 }} />
              )}
            </Box>
          )
        })}
        <div ref={bottom} />
      </Box>
      {error && (
        <Alert severity="error" variant="outlined" sx={{ mb: 1, whiteSpace: 'pre-line' }} data-testid="chat-error">
          {error}
        </Alert>
      )}
      <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-end' }}>
        <TextField
          fullWidth
          multiline
          maxRows={6}
          size="small"
          placeholder="質問を入力(Enterで送信、Shift+Enterで改行)"
          value={input}
          disabled={sending}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          slotProps={{ htmlInput: { 'data-testid': 'chat-input' } }}
        />
        <Button variant="contained" disabled={sending || !input.trim()} onClick={() => void send(input)}>
          送信
        </Button>
      </Stack>
    </Stack>
  )
}
