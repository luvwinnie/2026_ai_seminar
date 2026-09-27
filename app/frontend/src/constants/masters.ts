import type { MasterCategory } from '../types'

// マスタ対象6カテゴリ(docs/03 §2.5、docs/04 §2.5)。表示順もこの並び。
export const MASTER_CATEGORIES: MasterCategory[] = [
  'customer',
  'process',
  'machine',
  'operator',
  'phenomenon',
  'factor',
]

// カテゴリの日本語ラベル
export const MASTER_CATEGORY_LABELS: Record<MasterCategory, string> = {
  customer: '客先',
  process: '発生工程',
  machine: '使用機械',
  operator: '作業者',
  phenomenon: '現象分類',
  factor: '要因',
}

// マスタカテゴリ ⇔ ReportForm のフィールド名(候補提示に使用)
export const MASTER_CATEGORY_FIELD: Record<MasterCategory, string> = {
  customer: 'customer',
  process: 'process',
  machine: 'machine_name',
  operator: 'operator_name',
  phenomenon: 'phenomenon',
  factor: 'factor',
}
