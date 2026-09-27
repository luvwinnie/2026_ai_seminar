/**
 * ChatPanel — AIチャットの本体(共通コンポーネント)。
 *
 * - compact=true : Layout の常駐サイドパネル(3カラムの中央)。ヘッダは小型で、
 *   セッション履歴はメニューから選択。ルート遷移してもアンマウントされないため、
 *   WebMCP(ui_navigate / ui_open_report)でAIがメイン画面を切り替えている間も
 *   ストリーミングが途切れない。
 * - compact=false: 従来の全画面チャットページ(/chat)。セッション一覧を左に表示。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  IconButton,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import SendIcon from '@mui/icons-material/Send'
import SmartToyIcon from '@mui/icons-material/SmartToy'
import PersonIcon from '@mui/icons-material/Person'
import BuildIcon from '@mui/icons-material/BuildOutlined'
import CheckCircleIcon from '@mui/icons-material/CheckCircleOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlineOutlined'
import HourglassIcon from '@mui/icons-material/HourglassEmpty'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import AddCommentIcon from '@mui/icons-material/AddCommentOutlined'
import DeleteIcon from '@mui/icons-material/DeleteOutlineOutlined'
import HistoryIcon from '@mui/icons-material/History'
import KeyboardDoubleArrowLeftIcon from '@mui/icons-material/KeyboardDoubleArrowLeft'
import { useTheme } from '@mui/material/styles'
import PageHeader from './PageHeader'
import { streamChat } from '../api/chatStream'
import { deleteChatSession, fetchChatSession, fetchChatSessions } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { ChatSession, ChatSessionMessage, ChatSource, ChatToolEvent } from '../types'
import { MONO_FONT } from '../theme'
import MarkdownMessage from './MarkdownMessage'
import MicButton from './MicButton'
import FeedbackButtons from './FeedbackButtons'

interface DisplayMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  tools?: ChatToolEvent[]
  thinking?: string
  traceId?: string | null // Langfuse トレースID(フィードバック紐づけ用)
}

// ツール名の先頭サーバ接頭辞("defect-reports_" 等、最初の "_" まで)を除去して表示する
function shortToolName(name: string): string {
  const i = name.indexOf('_')
  return i >= 0 ? name.slice(i + 1) : name
}

// 同名ツールは状態を上書き、初出は末尾に追加
function upsertTool(tools: ChatToolEvent[], tool: ChatToolEvent): ChatToolEvent[] {
  const idx = tools.findIndex((t) => t.name === tool.name)
  if (idx === -1) return [...tools, tool]
  const next = tools.slice()
  next[idx] = tool
  return next
}

// セッション詳細のメッセージを表示用にマップ。履歴のツールは完了扱い(エラーは保持)。
function toDisplayMessage(m: ChatSessionMessage): DisplayMessage {
  return {
    role: m.role,
    content: m.content,
    sources: m.sources ?? undefined,
    tools: (m.tools ?? []).map((t) => ({
      ...t,
      status: t.status === 'error' ? 'error' : 'completed',
    })),
    thinking: m.thinking ?? undefined,
  }
}

// セッションの更新日時を M/D 表記に
function sessionDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}/${d.getDate()}`
}


const SUGGESTIONS = [
  'GENOS M560-Vで最近多い不具合は?',
  '寸法公差外れの主な原因と対策を教えて',
  'ダッシュボードを画面に出して',
]

// セッション一覧の1行(選択=アンバーのハイライト、ホバーで削除)
function SessionRow({
  session,
  selected,
  onSelect,
  onDelete,
}: {
  session: ChatSession
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const { palette } = useTheme()
  const tint = `${palette.primary.main}1F`
  return (
    <Box
      onClick={onSelect}
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        px: 1,
        py: 0.75,
        mb: 0.25,
        borderRadius: 1.5,
        cursor: 'pointer',
        borderLeft: '3px solid transparent',
        ...(selected ? { bgcolor: tint, borderLeftColor: palette.primary.main } : {}),
        '&:hover': { bgcolor: selected ? tint : 'action.hover' },
        '&:hover .session-del': { opacity: 1 },
      }}
    >
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Typography variant="body2" noWrap sx={{ fontWeight: selected ? 700 : 500 }}>
          {session.title || '(無題)'}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {sessionDate(session.updated_at)} · {session.message_count}件
        </Typography>
      </Box>
      <Tooltip title="削除">
        <IconButton
          className="session-del"
          size="small"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          sx={{ opacity: { xs: 1, md: 0 }, transition: 'opacity 150ms ease' }}
          aria-label="チャットを削除"
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Box>
  )
}

export default function ChatPanel({
  compact = false,
  onCollapse,
}: {
  compact?: boolean
  onCollapse?: () => void
}) {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // セッション履歴
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null)
  const [pendingDelete, setPendingDelete] = useState<ChatSession | null>(null)
  const [deleting, setDeleting] = useState(false)
  // compact モードの履歴メニュー
  const [historyAnchor, setHistoryAnchor] = useState<HTMLElement | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const reloadSessions = useCallback(() => {
    // 一覧取得の失敗は致命的でないため握りつぶす
    fetchChatSessions()
      .then(setSessions)
      .catch(() => undefined)
  }, [])

  useEffect(() => reloadSessions(), [reloadSessions])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  const newChat = () => {
    if (streaming) return
    setCurrentSessionId(null)
    setMessages([])
    setError(null)
    setInput('')
  }

  const selectSession = async (id: number) => {
    if (streaming || id === currentSessionId) return
    setError(null)
    try {
      const detail = await fetchChatSession(id)
      setMessages(detail.messages.map(toDisplayMessage))
      setCurrentSessionId(id)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteChatSession(pendingDelete.id)
      if (pendingDelete.id === currentSessionId) newChat()
      setPendingDelete(null)
      reloadSessions()
    } catch (e) {
      setError(errorMessage(e))
      setPendingDelete(null)
    } finally {
      setDeleting(false)
    }
  }

  const send = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || streaming) return

    setError(null)
    setInput('')

    // ユーザー発言 + 空のアシスタント発言(ストリームで埋める)を追加
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: trimmed },
      { role: 'assistant', content: '', sources: undefined, tools: [], thinking: '' },
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

    // 履歴はサーバ側で管理するため session_id のみ渡す
    streamChat(
      trimmed,
      currentSessionId,
      {
        onSession: (s) => {
          setCurrentSessionId(s.id)
          reloadSessions()
        },
        onSources: (sources) => updateLast((m) => ({ ...m, sources })),
        onToken: (t) => updateLast((m) => ({ ...m, content: m.content + t })),
        onTool: (tool) => updateLast((m) => ({ ...m, tools: upsertTool(m.tools ?? [], tool) })),
        onThinking: (t) => updateLast((m) => ({ ...m, thinking: (m.thinking ?? '') + t })),
        onDone: (traceId) => {
          updateLast((m) => ({ ...m, traceId }))
          setStreaming(false)
          reloadSessions()
        },
        onError: (detail) => {
          setError(detail)
          setStreaming(false)
        },
      },
      controller.signal,
    )
  }

  const messagesPane = (
    <Paper
      ref={scrollRef}
      variant="outlined"
      sx={{ flex: 1, overflowY: 'auto', p: compact ? 1.5 : 2, bgcolor: 'background.default', borderRadius: 2 }}
    >
      {messages.length === 0 && (
        <Box sx={{ textAlign: 'center', py: compact ? 4 : 6, color: 'text.secondary' }}>
          <SmartToyIcon sx={{ fontSize: compact ? 38 : 48, color: 'primary.main', mb: 1 }} />
          <Typography sx={{ fontWeight: 700 }}>質問を入力してください</Typography>
          <Typography variant="body2" sx={{ mb: 2 }}>
            報告書を検索して [KZ25-XXXX] 引用付きで回答。
            {compact && '「〜を画面に出して」で右の画面も操作できます。'}
          </Typography>
          <Stack
            direction={compact ? 'column' : 'row'}
            spacing={1}
            sx={{ justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap' }}
          >
            {SUGGESTIONS.map((s) => (
              <Chip key={s} label={s} onClick={() => send(s)} clickable variant="outlined" />
            ))}
          </Stack>
        </Box>
      )}

      <Stack spacing={2}>
        {messages.map((m, i) => (
          <Box key={i}>
            <MessageBubble
              message={m}
              streaming={streaming && i === messages.length - 1}
              compact={compact}
            />
            {/* 完了済みアシスタント回答への 👍/👎(品質ループ) */}
            {m.role === 'assistant' && m.content && !(streaming && i === messages.length - 1) && (
              <Box sx={{ pl: 5.5 }}>
                <FeedbackButtons
                  sessionId={currentSessionId}
                  messageIndex={i}
                  traceId={m.traceId}
                  answer={m.content}
                  question={messages[i - 1]?.role === 'user' ? messages[i - 1].content : undefined}
                />
              </Box>
            )}
          </Box>
        ))}
      </Stack>
    </Paper>
  )

  const inputForm = (
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
      {/* B-6 音声入力(Web Speech API 対応ブラウザのみ表示) */}
      <MicButton onText={(t) => setInput((v) => v + t)} disabled={streaming} />
      <IconButton type="submit" color="primary" disabled={streaming || !input.trim()} sx={{ mb: 0.5 }}>
        {streaming ? <CircularProgress size={22} /> : <SendIcon />}
      </IconButton>
    </Box>
  )

  const deleteDialog = (
    <Dialog open={Boolean(pendingDelete)} onClose={() => setPendingDelete(null)} maxWidth="xs">
      <DialogTitle>チャットを削除しますか?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          「{pendingDelete?.title || '(無題)'}」を削除します。この操作は取り消せません。
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setPendingDelete(null)} disabled={deleting}>
          キャンセル
        </Button>
        <Button color="error" variant="contained" onClick={confirmDelete} disabled={deleting}>
          {deleting ? '削除中…' : '削除する'}
        </Button>
      </DialogActions>
    </Dialog>
  )

  // ---------------- compact: 常駐サイドパネル ----------------
  if (compact) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', p: 1.5, gap: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, pb: 1 }}>
          <SmartToyIcon sx={{ color: 'primary.main', fontSize: 20 }} />
          <Typography sx={{ fontWeight: 800, fontSize: 14, flex: 1 }}>AIアシスタント</Typography>
          <Tooltip title="新しいチャット">
            <span>
              <IconButton size="small" onClick={newChat} disabled={streaming} aria-label="新しいチャット">
                <AddCommentIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="履歴">
            <IconButton
              size="small"
              onClick={(e) => setHistoryAnchor(e.currentTarget)}
              aria-label="チャット履歴"
            >
              <HistoryIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {onCollapse && (
            <Tooltip title="パネルをたたむ">
              <IconButton size="small" onClick={onCollapse} aria-label="チャットパネルをたたむ">
                <KeyboardDoubleArrowLeftIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>

        <Menu
          anchorEl={historyAnchor}
          open={Boolean(historyAnchor)}
          onClose={() => setHistoryAnchor(null)}
          slotProps={{ paper: { sx: { width: 300, maxHeight: 380 } } }}
        >
          {sessions.length === 0 && (
            <MenuItem disabled>
              <ListItemText primary="履歴はまだありません" />
            </MenuItem>
          )}
          {sessions.map((s) => (
            <MenuItem
              key={s.id}
              selected={s.id === currentSessionId}
              onClick={() => {
                setHistoryAnchor(null)
                selectSession(s.id)
              }}
              sx={{ '&:hover .session-del': { opacity: 1 } }}
            >
              <ListItemText
                primary={s.title || '(無題)'}
                secondary={`${sessionDate(s.updated_at)} · ${s.message_count}件`}
                slotProps={{
                  primary: { noWrap: true, sx: { fontSize: 13, fontWeight: s.id === currentSessionId ? 700 : 500 } },
                  secondary: { sx: { fontSize: 11 } },
                }}
              />
              <IconButton
                className="session-del"
                size="small"
                edge="end"
                onClick={(e) => {
                  e.stopPropagation()
                  setHistoryAnchor(null)
                  setPendingDelete(s)
                }}
                sx={{ opacity: 0, transition: 'opacity 150ms ease' }}
                aria-label="チャットを削除"
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </MenuItem>
          ))}
        </Menu>

        <Divider sx={{ mb: 1 }} />
        {messagesPane}
        {error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
        {inputForm}
        {deleteDialog}
      </Box>
    )
  }

  // ---------------- page: 全画面チャット(/chat) ----------------
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 130px)' }}>
      <PageHeader
        title="AIチャット"
        subtitle="不適合報告書データに基づく品質保証AIアシスタント(RAG)"
        action={
          <Button
            variant="outlined"
            size="small"
            startIcon={<AddCommentIcon />}
            onClick={newChat}
            disabled={streaming}
            sx={{ display: { xs: 'inline-flex', md: 'none' } }}
          >
            新しいチャット
          </Button>
        }
      />

      <Box sx={{ display: 'flex', gap: 1.5, flex: 1, minHeight: 0 }}>
        {/* セッション一覧(md+ で表示) */}
        <Box
          sx={{
            width: 240,
            flexShrink: 0,
            display: { xs: 'none', md: 'flex' },
            flexDirection: 'column',
          }}
        >
          <Button
            variant="outlined"
            fullWidth
            startIcon={<AddCommentIcon />}
            onClick={newChat}
            disabled={streaming}
            sx={{ mb: 1 }}
          >
            新しいチャット
          </Button>
          <Paper variant="outlined" sx={{ flex: 1, overflowY: 'auto', borderRadius: 2, p: 0.5 }}>
            {sessions.length === 0 ? (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', p: 1.5, textAlign: 'center' }}
              >
                履歴はまだありません
              </Typography>
            ) : (
              sessions.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  selected={s.id === currentSessionId}
                  onSelect={() => selectSession(s.id)}
                  onDelete={() => setPendingDelete(s)}
                />
              ))
            )}
          </Paper>
        </Box>

        {/* チャットペイン */}
        <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          {messagesPane}
          {error && (
            <Alert severity="error" sx={{ mt: 1 }}>
              {error}
            </Alert>
          )}
          {inputForm}
        </Box>
      </Box>

      {deleteDialog}
    </Box>
  )
}

// ツール使用の状態一覧(AIメッセージ上部の「アクティビティ」領域)
function ToolActivity({ tools }: { tools: ChatToolEvent[] }) {
  if (tools.length === 0) return null
  return (
    <Box sx={{ mb: 0.75, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
      {tools.map((t) => {
        let statusIcon
        if (t.status === 'running') statusIcon = <CircularProgress size={13} />
        else if (t.status === 'completed')
          statusIcon = <CheckCircleIcon sx={{ fontSize: 15, color: 'success.main' }} />
        else if (t.status === 'error')
          statusIcon = <ErrorOutlineIcon sx={{ fontSize: 15, color: 'error.main' }} />
        else statusIcon = <HourglassIcon sx={{ fontSize: 14, color: 'text.disabled' }} />
        return (
          <Box key={t.name} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
            <Box sx={{ width: 16, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
              {statusIcon}
            </Box>
            <BuildIcon sx={{ fontSize: 13, color: 'text.secondary' }} />
            <Typography
              variant="caption"
              sx={{
                fontFamily: MONO_FONT,
                fontWeight: 600,
                color: t.status === 'error' ? 'error.main' : 'text.primary',
              }}
            >
              {shortToolName(t.name)}
            </Typography>
            {t.title && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                · {t.title}
              </Typography>
            )}
          </Box>
        )
      })}
    </Box>
  )
}

// 思考(推論)ブロック。既定は折りたたみ。live=本文到着前は最新行のプレビューを表示。
function ThinkingBlock({ text, live }: { text: string; live: boolean }) {
  const { palette } = useTheme()
  const [open, setOpen] = useState(false)
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  const preview = (lines[lines.length - 1] ?? '').slice(0, 60)
  return (
    <Box sx={{ mb: 0.75 }}>
      <Box
        role="button"
        tabIndex={0}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen((o) => !o)
          }
        }}
        sx={{
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.25,
          color: 'text.secondary',
          userSelect: 'none',
        }}
      >
        <Typography variant="caption" sx={{ fontWeight: 600 }}>
          💭 思考{open ? 'を隠す' : 'を表示'}
        </Typography>
        {open ? <ExpandLessIcon sx={{ fontSize: 16 }} /> : <ExpandMoreIcon sx={{ fontSize: 16 }} />}
      </Box>
      {live && !open && preview && (
        <Typography
          variant="caption"
          sx={{ display: 'block', mt: 0.25, color: 'text.secondary', fontStyle: 'italic' }}
        >
          思考中… {preview}
        </Typography>
      )}
      <Collapse in={open}>
        <Box
          sx={{
            mt: 0.5,
            p: 1,
            borderRadius: 1,
            bgcolor: palette.app.base,
            border: `1px solid ${palette.app.hairline}`,
            maxHeight: 240,
            overflowY: 'auto',
          }}
        >
          <Typography
            variant="caption"
            component="div"
            sx={{ whiteSpace: 'pre-wrap', color: 'text.secondary', lineHeight: 1.6 }}
          >
            {text}
          </Typography>
        </Box>
      </Collapse>
    </Box>
  )
}

function MessageBubble({
  message,
  streaming,
  compact,
}: {
  message: DisplayMessage
  streaming: boolean
  compact?: boolean
}) {
  const { palette } = useTheme()
  const isUser = message.role === 'user'
  const hasActivity = Boolean(message.thinking) || (message.tools?.length ?? 0) > 0
  return (
    <Box sx={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', gap: compact ? 1 : 1.5, alignItems: 'flex-start' }}>
      <Avatar sx={{ bgcolor: isUser ? 'primary.main' : 'secondary.main', width: compact ? 28 : 34, height: compact ? 28 : 34 }}>
        {isUser ? <PersonIcon fontSize="small" /> : <SmartToyIcon fontSize="small" />}
      </Avatar>
      <Box sx={{ maxWidth: compact ? '88%' : '78%' }}>
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
                label={compact ? s.defect_id : `${s.defect_id} · ${s.part_name}`}
                title={`${s.phenomenon}｜${s.snippet}`}
                color="primary"
                variant="outlined"
              />
            ))}
          </Stack>
        )}

        {/* アクティビティ(ツール使用)と思考の可視化 */}
        {!isUser && message.tools && message.tools.length > 0 && (
          <ToolActivity tools={message.tools} />
        )}
        {!isUser && message.thinking && (
          <ThinkingBlock text={message.thinking} live={streaming && !message.content} />
        )}

        <Paper
          elevation={0}
          sx={{
            px: 1.75,
            py: 1.25,
            bgcolor: isUser ? 'primary.main' : palette.app.elevated,
            color: isUser ? 'primary.contrastText' : 'text.primary',
            border: isUser ? 'none' : `1px solid ${palette.app.hairline}`,
            borderRadius: 2,
            whiteSpace: isUser ? 'pre-wrap' : 'normal',
            wordBreak: 'break-word',
            lineHeight: 1.7,
            fontSize: compact ? 14 : undefined,
          }}
        >
          {isUser ? (
            message.content
          ) : message.content ? (
            <MarkdownMessage text={message.content} />
          ) : streaming && hasActivity ? (
            // ツール実行/思考が進行中: フリーズに見えないよう控えめに提示
            <Typography variant="body2" color="text.secondary">
              回答を生成しています…
            </Typography>
          ) : streaming ? (
            // 送信直後〜最初のイベントまで: 従来のスピナー
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
