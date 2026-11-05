// API の呼び出し（04_API設計書.md）。相対パスで呼び、開発では Vite のプロキシが backend へ渡す。

export interface Report {
  id: number
  defect_id: string
  occurrence_date: string
  report_date: string | null
  customer: string
  discoverer: string | null
  process: string
  machine_name: string
  operator_name: string
  part_number: string
  part_name: string
  production_count: number
  defect_count: number
  defect_rate: number | null
  defect_description: string
  good_condition: string | null
  phenomenon: string
  cause: string | null
  factor: string | null
  category_4m: string | null
  severity: string
  status: string
  countermeasure: string | null
  material_cost: number | null
  processing_cost: number | null
  outsourcing_cost: number | null
  other_cost: number | null
  total_cost: number | null
  is_recurrence: boolean | null
  has_procedure: boolean | null
  notes: string | null
  created_at: string
  updated_at: string | null
}

export interface ReportList {
  total: number
  items: Report[]
}

export interface Master {
  id: number
  category: string
  name: string
  sort_order: number
  is_active: boolean
  usage_count: number
}

export type Masters = Record<'customer' | 'process' | 'machine' | 'operator' | 'phenomenon' | 'factor', Master[]>

export interface Health {
  status: string
  reports: number
}

// 失敗の理由。status が null のときは、backend とつながらなかった
export class ApiError extends Error {
  status: number | null

  constructor(message: string, status: number | null) {
    super(message)
    this.status = status
  }
}

interface ValidationItem {
  type: string
  loc: (string | number)[]
  msg: string
}

const PARAM_LABELS: Record<string, string> = {
  date_from: '開始日',
  date_to: '終了日',
  limit: '表示件数',
  offset: '開始位置',
}

// FastAPI 標準の 422（detail の配列）を日本語の理由にする
function translateValidationItem(item: ValidationItem): string {
  const param = String(item.loc[item.loc.length - 1])
  const label = PARAM_LABELS[param] ?? param
  if (item.type === 'date_range') return '開始日が終了日より後です。開始日を終了日以前にしてください。'
  if (item.type.startsWith('date')) return `${label}が日付として読めません（YYYY-MM-DD の形で、ある日付を入れてください）。`
  if (item.type === 'greater_than_equal' || item.type === 'less_than_equal') return `${label}が範囲の外です。`
  return `${label}の値が正しくありません。`
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => translateValidationItem(item as ValidationItem)).join('\n')
  return `サーバーから正しい応答がありませんでした（HTTP ${status}）。バックエンドが動いているか確かめてください。`
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { signal })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('バックエンドに接続できません（通信に失敗しました）。', null)
  }
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // 本文が JSON でない（プロキシの先の backend が止まっているときなど）
    }
    throw new ApiError(errorMessage(response.status, body), response.status)
  }
  return (await response.json()) as T
}

export function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(String(error), null)
}

export const getHealth = () => fetchJson<Health>('/health')
export const getMasters = (signal?: AbortSignal) => fetchJson<Masters>('/api/masters', signal)
export const getReports = (query: string, signal?: AbortSignal) =>
  fetchJson<ReportList>(`/api/reports?${query}`, signal)
export const getReport = (defectId: string, signal?: AbortSignal) =>
  fetchJson<Report>(`/api/reports/${encodeURIComponent(defectId)}`, signal)
