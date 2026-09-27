/**
 * 報告書トリアージ(判断モデル Jev)の表示用の定数とフック。部品は components/triageCommon.tsx。
 */
import { useEffect, useState } from 'react'
import { fetchTriageStatus } from '../api/endpoints'
import type { TriageStatus } from '../types'
import { CATEGORY_4M_LABELS, SEVERITY_LABELS } from '../constants/vocab'

export const FIELD_LABELS: Record<string, string> = {
  phenomenon: '現象分類',
  factor: '要因',
  category_4m: '4M分類',
  severity: '重要度',
  systemic: '仕組みの原因(再発のおそれ)',
  outflow: '客先流出',
  info_missing: '記述不足',
}

export const SOURCE_LABELS: Record<string, string> = {
  jev: 'Jev',
  llm: 'LLM',
  rule: 'コード',
}

export function valueLabel(field: string, value: string | null | undefined): string {
  if (!value) return '(判断できず)'
  if (field === 'category_4m') return CATEGORY_4M_LABELS[value] ?? value
  if (field === 'severity') return SEVERITY_LABELS[value as keyof typeof SEVERITY_LABELS] ?? value
  return value
}

/** トリアージが使えるか(JEV_ENABLED とキー)。使えなければ部品ごと出さない。 */
export function useTriageStatus(): TriageStatus | null {
  const [status, setStatus] = useState<TriageStatus | null>(null)
  useEffect(() => {
    let alive = true
    fetchTriageStatus()
      .then((s) => alive && setStatus(s))
      .catch(() => alive && setStatus(null))
    return () => {
      alive = false
    }
  }, [])
  return status
}
