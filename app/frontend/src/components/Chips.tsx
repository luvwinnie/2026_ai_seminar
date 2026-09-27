import { Chip } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import type { Severity, Status } from '../types'
import { SEVERITY_LABELS, STATUS_LABELS } from '../constants/vocab'

// outlined + 薄い下地。文字と枠は意味色、背景はその低透明度(両モードで馴染む)。
function tintedChipSx(hex: string) {
  return {
    color: hex,
    bgcolor: `${hex}1F`, // ~12% の下地
    border: `1px solid ${hex}66`, // ~40% の枠
    fontWeight: 600,
  }
}

/** 重要度チップ(意味色・モード対応) */
export function SeverityChip({ severity }: { severity: Severity }) {
  const { palette } = useTheme()
  const hex = palette.chart.severity[severity] ?? palette.text.disabled
  return <Chip size="small" label={SEVERITY_LABELS[severity] ?? severity} sx={tintedChipSx(hex)} />
}

/** ステータスチップ(意味色・モード対応) */
export function StatusChip({ status }: { status: Status }) {
  const { palette } = useTheme()
  const hex = palette.chart.status[status] ?? palette.text.disabled
  return <Chip size="small" label={STATUS_LABELS[status] ?? status} sx={tintedChipSx(hex)} />
}
