// 固定列挙の語彙。docs/03_データモデル設計書.md §2 のフィールド定義に準拠。
// customer/process/machine/operator/phenomenon/factor は DB マスタ(§2.5)化したため、
// 選択肢は API(useMasters)から取得する。ここには固定列挙(severity/status/4M)のみを残す。

import type { Severity, Status, Category4M } from '../types'

export const CATEGORIES_4M: Category4M[] = ['Man', 'Machine', 'Material', 'Method']

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']
export const STATUSES: Status[] = ['open', 'in_progress', 'completed']

// 表示用の日本語ラベル
export const SEVERITY_LABELS: Record<Severity, string> = {
  critical: '緊急',
  high: '高',
  medium: '中',
  low: '低',
}

export const STATUS_LABELS: Record<Status, string> = {
  open: '未対応',
  in_progress: '対応中',
  completed: '完了',
}

// severity / status の意味色(hex)は theme.ts の
// SEVERITY_CHART_COLORS / STATUS_CHART_COLORS に集約している。

export const CATEGORY_4M_LABELS: Record<string, string> = {
  Man: '人 (Man)',
  Machine: '機械 (Machine)',
  Material: '材料 (Material)',
  Method: '方法 (Method)',
}
