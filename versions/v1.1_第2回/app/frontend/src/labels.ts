// コード値の日本語と、値の書き方（05_UI設計書.md §1・S2）

export const SEVERITY_LABELS: Record<string, string> = {
  critical: '重大',
  high: '高',
  medium: '中',
  low: '低',
}

export const STATUS_LABELS: Record<string, string> = {
  open: '未対応',
  in_progress: '対応中',
  completed: '完了',
}

export const CATEGORY_4M_LABELS: Record<string, string> = {
  Man: '人',
  Machine: '機械',
  Material: '材料',
  Method: '方法',
}

export const DASH = '—'

export function show(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? DASH : String(value)
}

// 不良率は小数2桁の %（0.25 → 25.00%）
export function formatPercent(rate: number | null): string {
  return rate === null ? DASH : `${(rate * 100).toFixed(2)}%`
}

// 金額は ¥ と3桁区切り
export function formatYen(value: number | null): string {
  return value === null ? DASH : `¥${value.toLocaleString('ja-JP', { maximumFractionDigits: 0 })}`
}

export function format4M(value: string | null): string {
  return value ? `${CATEGORY_4M_LABELS[value] ?? value} (${value})` : '未分類'
}
