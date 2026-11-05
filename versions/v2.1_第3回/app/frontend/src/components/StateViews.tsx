import { Alert, AlertTitle, Button, CircularProgress, Stack, Typography } from '@mui/material'

// 画面の状態は、この3つだけで出す（05_UI設計書.md §5）

export function Loading() {
  return (
    <Stack role="status" spacing={2} sx={{ py: 8, alignItems: 'center' }}>
      <CircularProgress />
      <Typography color="text.secondary">読み込み中…</Typography>
    </Stack>
  )
}

export function EmptyState({ message = '条件に一致する報告書がありません' }: { message?: string }) {
  return (
    <Typography data-testid="empty-state" color="text.secondary" align="center" sx={{ py: 6 }}>
      {message}
    </Typography>
  )
}

interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
}

export function ErrorState({ title = '読み込みに失敗しました', message, onRetry }: ErrorStateProps) {
  return (
    <Alert
      severity="error"
      variant="outlined"
      data-testid="error-state"
      action={
        onRetry && (
          <Button color="inherit" onClick={onRetry}>
            再試行
          </Button>
        )
      }
    >
      <AlertTitle>{title}</AlertTitle>
      <Typography variant="body2" sx={{ whiteSpace: 'pre-line' }}>
        {message}
      </Typography>
    </Alert>
  )
}
