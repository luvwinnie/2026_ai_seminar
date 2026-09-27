// 表示用のフォーマットヘルパー

export function formatCurrency(value?: number | null): string {
  if (value == null) return '—'
  return `¥${Math.round(value).toLocaleString('ja-JP')}`
}

export function formatPercent(ratio?: number | null, digits = 1): string {
  if (ratio == null) return '—'
  return `${(ratio * 100).toFixed(digits)}%`
}

export function formatNumber(value?: number | null): string {
  if (value == null) return '—'
  return value.toLocaleString('ja-JP')
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  // occurrence_date 等は 'YYYY-MM-DD'。datetime は先頭10文字で日付表示。
  return value.slice(0, 10)
}

/** 文字列を linkify 用に [KZ25-XXXX] トークンで分割する */
const DR_PATTERN = /(KZ25-\d{4})/g

export function splitDefectIds(text: string): { text: string; isDefectId: boolean }[] {
  return text.split(DR_PATTERN).map((part) => ({
    text: part,
    isDefectId: /^KZ25-\d{4}$/.test(part),
  }))
}
