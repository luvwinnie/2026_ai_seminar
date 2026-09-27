// 語彙リスト。docs/03_データモデル設計書.md §2 のフィールド定義に準拠。
// 手動入力フォームのセレクトやフィルタで使用する。

import type { Severity, Status, Category4M } from '../types'

export const PROCESSES = [
  '旋盤',
  'フライス',
  'マシニング',
  '研磨',
  '溶接',
  '組立',
  '検査',
  'バリ取り',
] as const

export const MACHINES = [
  'QUICK TURN 250MSY',
  'GENOS M560-V',
  'GENOS M660-V',
  'VARIAXIS i-800 NEO',
  'TSL-550',
  'MX-520',
  'WT-150II',
  'YZ-8WR',
  '汎用フライス',
] as const

export const PHENOMENA = [
  '寸法不良',
  '穴位置不良',
  'キズ',
  'バリ',
  '面粗度不良',
  '工具折損',
  '刻印不良',
  '段差',
  '変形',
  '欠け',
  '取付ミス',
  'プログラムミス',
] as const

export const FACTORS = [
  '確認不足',
  '知識不足',
  '経験不足',
  '手順逸脱',
  '工具摩耗',
  '機械故障',
  'プログラム誤り',
  '材料不良',
  '図面誤読',
  '連絡不足',
] as const

export const CATEGORIES_4M: Category4M[] = ['Man', 'Machine', 'Material', 'Method']

export const CUSTOMERS = [
  '翠峰重工業',
  '六花電機工業',
  '蒼井田機器工業',
  '遠原精密工業',
  '汐峰造機',
  '楠里ポンプ工業',
  '深名電子工業',
  '綿鍋機工',
  '鷹森航空部品',
  '霞岡バルブ工業',
] as const

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

// MUI Chip の色マッピング
export const SEVERITY_COLORS: Record<Severity, 'error' | 'warning' | 'info' | 'success'> = {
  critical: 'error',
  high: 'warning',
  medium: 'info',
  low: 'success',
}

export const STATUS_COLORS: Record<Status, 'default' | 'primary' | 'success'> = {
  open: 'default',
  in_progress: 'primary',
  completed: 'success',
}

export const CATEGORY_4M_LABELS: Record<string, string> = {
  Man: '人 (Man)',
  Machine: '機械 (Machine)',
  Material: '材料 (Material)',
  Method: '方法 (Method)',
}
