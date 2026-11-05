import { useCallback, useEffect, useState } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material'
import { useTheme } from '@mui/material/styles'
import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import { deleteChatSession, getChatSessions, toApiError, type ChatSession } from '../api'
import ChatPanel from '../components/ChatPanel'
import { ErrorState } from '../components/StateViews'

// S3 AI チャット（/chat）。左に会話の一覧、右に対話（05_UI設計書.md S3）

function formatUpdated(value: string): string {
  const d = new Date(value)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function ChatPage() {
  const theme = useTheme()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [toDelete, setToDelete] = useState<ChatSession | null>(null)
  // 「新しいチャット」で ChatPanel を作り直す（前の会話の表示や理由を残さない）
  const [panelKey, setPanelKey] = useState(0)

  const newChat = () => {
    setSelected(null)
    setPanelKey((k) => k + 1)
  }

  const loadSessions = useCallback(() => {
    getChatSessions()
      .then((items) => {
        setSessions(items)
        setListError(null)
      })
      .catch((e) => setListError(toApiError(e).message))
  }, [])

  useEffect(loadSessions, [loadSessions])

  const confirmDelete = async () => {
    if (!toDelete) return
    try {
      await deleteChatSession(toDelete.id)
      if (selected === toDelete.id) newChat()
    } catch (e) {
      setListError(toApiError(e).message)
    }
    setToDelete(null)
    loadSessions()
  }

  return (
    <Stack direction="row" spacing={2} sx={{ height: 'calc(100vh - 48px)' }}>
      <Box sx={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <Button variant="outlined" startIcon={<AddIcon />} onClick={newChat} sx={{ mb: 1 }}>
          新しいチャット
        </Button>
        {listError && <ErrorState title="会話の一覧を読めませんでした" message={listError} onRetry={loadSessions} />}
        <List dense sx={{ overflowY: 'auto' }} data-testid="session-list">
          {sessions.map((s) => (
            <ListItemButton
              key={s.id}
              selected={s.id === selected}
              onClick={() => setSelected(s.id)}
              data-testid="session-item"
              sx={{
                borderLeft: '3px solid transparent',
                '&.Mui-selected': { borderLeftColor: theme.palette.primary.main },
                // 行にマウスを載せたときだけ削除のボタンを出す
                '& .delete-button': { visibility: 'hidden' },
                '&:hover .delete-button': { visibility: 'visible' },
              }}
            >
              <ListItemText
                primary={s.title ?? '新しい会話'}
                secondary={`${formatUpdated(s.updated_at)} · ${s.message_count}件`}
                slotProps={{ primary: { noWrap: true } }}
              />
              <IconButton
                className="delete-button"
                size="small"
                aria-label="削除"
                onClick={(e) => {
                  e.stopPropagation()
                  setToDelete(s)
                }}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </ListItemButton>
          ))}
        </List>
      </Box>
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
          AIチャット
        </Typography>
        <Box sx={{ flex: 1, minHeight: 0 }}>
          <ChatPanel key={panelKey} sessionId={selected} onSessionCreated={setSelected} onTurnFinished={loadSessions} />
        </Box>
      </Box>
      <Dialog open={toDelete !== null} onClose={() => setToDelete(null)}>
        <DialogTitle>会話を削除しますか？</DialogTitle>
        <DialogContent>
          <Typography>「{toDelete?.title}」とその発言を消します。元には戻せません。</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setToDelete(null)}>キャンセル</Button>
          <Button color="error" variant="contained" onClick={() => void confirmDelete()}>
            削除
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  )
}
