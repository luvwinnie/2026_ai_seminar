import { Chip } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { SEVERITY_LABELS, STATUS_LABELS } from '../labels'

// 重大度・状態は色だけに頼らず、ラベル付きのチップにする

export function SeverityChip({ value }: { value: string }) {
  const theme = useTheme()
  const color = theme.palette.app.severity[value as keyof typeof theme.palette.app.severity] ?? theme.palette.text.secondary
  return <Chip size="small" variant="outlined" label={SEVERITY_LABELS[value] ?? value} sx={{ color, borderColor: color }} />
}

export function StatusChip({ value }: { value: string }) {
  const theme = useTheme()
  const color = theme.palette.app.status[value as keyof typeof theme.palette.app.status] ?? theme.palette.text.secondary
  return <Chip size="small" variant="outlined" label={STATUS_LABELS[value] ?? value} sx={{ color, borderColor: color }} />
}
