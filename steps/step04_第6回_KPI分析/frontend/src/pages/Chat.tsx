import { useEffect, useRef, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Avatar,
  Box,
  Chip,
  CircularProgress,
  IconButton,
  Link,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import SendIcon from '@mui/icons-material/Send'
import SmartToyIcon from '@mui/icons-material/SmartToy'
import PersonIcon from '@mui/icons-material/Person'
import PageHeader from '../components/PageHeader'
import { streamChat } from '../api/chatStream'
import type { ChatMessage, ChatSource } from '../types'
import { splitDefectIds } from '../utils/format'

// 直近何往復ぶんの履歴を送るか(docs/04: 直近10往復)
const MAX_HISTORY_PAIRS = 10

interface DisplayMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
}

// [KZ25-XXXX] を報告書詳細へのリンクに変換して描画する
function LinkifiedText({ text }: { text: string }) {
  return (
    <>
      {splitDefectIds(text).map((part, i) =>
        part.isDefectId ? (
          <Link key={i} component={RouterLink} to={`/reports/${part.text}`} sx={{ fontWeight: 700 }}>
            {part.text}
          </Link>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  )
}

const SUGGESTIONS = [
  'GENOS M560-Vで最近多い不具合は?',
  '寸法不良の主な原因と対策を教えて',
  '損失額が大きい報告書の傾向は?',
]

export default function Chat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  const send = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return

    setError(null)
    setInput('')

    // 送信する履歴(system が付ける前の user/assistant のみ、直近10往復)
    const history: ChatMessage[] = messages
      .slice(-MAX_HISTORY_PAIRS * 2)
      .map((m) => ({ role: m.role, content: m.content }))

    // ユーザー発言 + 空のアシスタント発言(ストリームで埋める)を追加
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: trimmed },
      { role: 'assistant', content: '', sources: undefined },
    ])
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller

    // 末尾のアシスタントメッセージを更新するヘルパー
    const updateLast = (fn: (m: DisplayMessage) => DisplayMessage) =>
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = fn(next[next.length - 1])
        return next
      })

    streamChat(
      trimmed,
      history,
      {
        onSources: (sources) => updateLast((m) => ({ ...m, sources })),
        onToken: (t) => updateLast((m) => ({ ...m, content: m.content + t })),
        onDone: () => setStreaming(false),
        onError: (detail) => {
          setError(detail)
          setStreaming(false)
        },
      },
      controller.signal,
    )
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 130px)' }}>
      <PageHeader title="AIチャット" subtitle="不適合報告書データに基づく品質保証AIアシスタント(RAG)" />

      <Paper
        ref={scrollRef}
        variant="outlined"
        sx={{ flex: 1, overflowY: 'auto', p: 2, bgcolor: '#f8fafc', borderRadius: 2 }}
      >
        {messages.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 6, color: 'text.secondary' }}>
            <SmartToyIcon sx={{ fontSize: 48, color: 'primary.main', mb: 1 }} />
            <Typography sx={{ fontWeight: 700 }}>質問を入力してください</Typography>
            <Typography variant="body2" sx={{ mb: 2 }}>
              報告書の内容を検索し、参照元 [KZ25-XXXX] を引用して回答します。
            </Typography>
            <Stack direction="row" spacing={1} sx={{ justifyContent: 'center', flexWrap: 'wrap' }}>
              {SUGGESTIONS.map((s) => (
                <Chip key={s} label={s} onClick={() => send(s)} clickable variant="outlined" />
              ))}
            </Stack>
          </Box>
        )}

        <Stack spacing={2}>
          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} streaming={streaming && i === messages.length - 1} />
          ))}
        </Stack>
      </Paper>

      {error && (
        <Alert severity="error" sx={{ mt: 1 }}>
          {error}
        </Alert>
      )}

      <Box
        component="form"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
        sx={{ display: 'flex', gap: 1, mt: 1.5, alignItems: 'flex-end' }}
      >
        <TextField
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="質問を入力(Enterで送信 / Shift+Enterで改行)"
          fullWidth
          multiline
          maxRows={4}
          size="small"
          disabled={streaming}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send(input)
            }
          }}
        />
        <IconButton type="submit" color="primary" disabled={streaming || !input.trim()} sx={{ mb: 0.5 }}>
          {streaming ? <CircularProgress size={22} /> : <SendIcon />}
        </IconButton>
      </Box>
    </Box>
  )
}

function MessageBubble({ message, streaming }: { message: DisplayMessage; streaming: boolean }) {
  const isUser = message.role === 'user'
  return (
    <Box sx={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: 1.5, alignItems: 'flex-start' }}>
      <Avatar sx={{ bgcolor: isUser ? 'primary.main' : 'secondary.main', width: 34, height: 34 }}>
        {isUser ? <PersonIcon fontSize="small" /> : <SmartToyIcon fontSize="small" />}
      </Avatar>
      <Box sx={{ maxWidth: '78%' }}>
        {/* 参照元チップ(回答の上に表示) */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', mb: 0.75 }}>
            {message.sources.map((s) => (
              <Chip
                key={s.defect_id}
                size="small"
                component={RouterLink}
                to={`/reports/${s.defect_id}`}
                clickable
                label={`${s.defect_id} · ${s.part_name}`}
                title={`${s.phenomenon}｜${s.snippet}`}
                color="primary"
                variant="outlined"
              />
            ))}
          </Stack>
        )}
        <Paper
          elevation={0}
          sx={{
            px: 1.75,
            py: 1.25,
            bgcolor: isUser ? 'primary.main' : '#fff',
            color: isUser ? '#fff' : 'text.primary',
            border: isUser ? 'none' : '1px solid #e2e8f0',
            borderRadius: 2,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: 1.7,
          }}
        >
          {isUser ? (
            message.content
          ) : message.content ? (
            <LinkifiedText text={message.content} />
          ) : streaming ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.secondary' }}>
              <CircularProgress size={14} />
              <Typography variant="body2">回答を生成中…</Typography>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              (応答なし)
            </Typography>
          )}
        </Paper>
      </Box>
    </Box>
  )
}
