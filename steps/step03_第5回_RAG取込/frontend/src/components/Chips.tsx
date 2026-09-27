import { Chip } from '@mui/material'
import type { Severity, Status } from '../types'
import {
  SEVERITY_COLORS,
  SEVERITY_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
} from '../constants/vocab'

/** 重要度チップ(色分け) */
export function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <Chip
      size="small"
      label={SEVERITY_LABELS[severity] ?? severity}
      color={SEVERITY_COLORS[severity] ?? 'default'}
      variant={severity === 'low' ? 'outlined' : 'filled'}
    />
  )
}

/** ステータスチップ(色分け) */
export function StatusChip({ status }: { status: Status }) {
  return (
    <Chip
      size="small"
      label={STATUS_LABELS[status] ?? status}
      color={STATUS_COLORS[status] ?? 'default'}
      variant={status === 'open' ? 'outlined' : 'filled'}
    />
  )
}
