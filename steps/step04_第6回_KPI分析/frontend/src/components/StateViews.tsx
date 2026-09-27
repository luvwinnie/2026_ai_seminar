import { Alert, Box, CircularProgress, Typography } from '@mui/material'

/** ローディング表示(中央寄せの CircularProgress) */
export function Loading({ label = '読み込み中…' }: { label?: string }) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        py: 8,
      }}
    >
      <CircularProgress />
      <Typography color="text.secondary" variant="body2">
        {label}
      </Typography>
    </Box>
  )
}

/** エラー表示(MUI Alert) */
export function ErrorState({ message }: { message: string }) {
  return (
    <Alert severity="error" sx={{ my: 2 }}>
      {message}
    </Alert>
  )
}

/** 空状態の表示 */
export function EmptyState({ message = 'データがありません' }: { message?: string }) {
  return (
    <Box sx={{ py: 6, textAlign: 'center' }}>
      <Typography color="text.secondary">{message}</Typography>
    </Box>
  )
}
