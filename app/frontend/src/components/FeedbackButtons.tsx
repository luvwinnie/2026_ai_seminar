/**
 * チャット回答への 👍/👎 フィードバック(試用者の声を集めて改善に回す品質ループ)。
 * 👍は即送信、👎は任意コメント付きで送信。送信後はお礼表示に置き換わる。
 * 保存先: POST /api/chat/feedback(週次ダイジェストに集計される)。
 */
import { useState } from 'react'
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import ThumbUpIcon from '@mui/icons-material/ThumbUpAltOutlined'
import ThumbDownIcon from '@mui/icons-material/ThumbDownAltOutlined'
import { sendChatFeedback } from '../api/endpoints'

export default function FeedbackButtons({
  sessionId,
  messageIndex,
  answer,
  question,
  traceId,
}: {
  sessionId: number | null
  messageIndex: number
  answer: string
  question?: string
  traceId?: string | null
}) {
  const [sent, setSent] = useState<null | 1 | -1>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (rating: 1 | -1, note?: string) => {
    setBusy(true)
    try {
      await sendChatFeedback({
        session_id: sessionId,
        message_index: messageIndex,
        trace_id: traceId ?? undefined,
        rating,
        comment: note,
        answer_excerpt: answer.slice(0, 500),
        question_excerpt: question?.slice(0, 300),
      })
      setSent(rating)
      setDialogOpen(false)
    } catch {
      /* フィードバック送信失敗は本体機能に影響させない */
      setSent(rating)
      setDialogOpen(false)
    } finally {
      setBusy(false)
    }
  }

  if (sent !== null) {
    return (
      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
        {sent === 1 ? '👍 評価を記録しました' : '👎 ご指摘ありがとうございました'}
      </Typography>
    )
  }

  return (
    <>
      <Stack direction="row" spacing={0} sx={{ mt: 0.25, alignItems: 'center' }}>
        <Tooltip title="役に立った">
          <IconButton size="small" onClick={() => submit(1)} disabled={busy} aria-label="役に立った">
            <ThumbUpIcon sx={{ fontSize: 15 }} />
          </IconButton>
        </Tooltip>
        <Tooltip title="問題を報告(根拠が違う・操作されていない等)">
          <IconButton size="small" onClick={() => setDialogOpen(true)} disabled={busy} aria-label="問題を報告">
            <ThumbDownIcon sx={{ fontSize: 15 }} />
          </IconButton>
        </Tooltip>
      </Stack>
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 16 }}>回答の問題を報告</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={2}
            placeholder="例: 引用された報告書と回答の内容が一致していない"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            size="small"
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={() => submit(-1, comment)} disabled={busy}>
            送信
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
