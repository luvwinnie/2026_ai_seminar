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
  chat_backend: 'opencode' | 'none'
}

// AI アシスタント（04_API設計書.md §6）
export interface ChatTool {
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  title: string | null
}

export interface ChatSession {
  id: number
  title: string | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  tools: ChatTool[] | null
  thinking: string | null
  created_at: string
}

export interface ChatSessionDetail {
  session: ChatSession
  messages: ChatMessage[]
}

// POST /api/chat/stream の SSE のイベント
export type ChatEvent =
  | { event: 'session'; data: { id: number; title: string } }
  | { event: 'thinking'; data: { text: string } }
  | { event: 'tool'; data: ChatTool }
  | { event: 'token'; data: { text: string } }
  | { event: 'done'; data: { trace_id: string | null } }
  | { event: 'error'; data: { detail: string } }

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

async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (error) {
    if (init?.signal?.aborted) throw error
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
  return response
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await request(path, { signal })
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

export const getChatSessions = (signal?: AbortSignal) => fetchJson<ChatSession[]>('/api/chat/sessions', signal)
export const getChatSession = (sessionId: number, signal?: AbortSignal) =>
  fetchJson<ChatSessionDetail>(`/api/chat/sessions/${sessionId}`, signal)
export const deleteChatSession = async (sessionId: number) => {
  await request(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' })
}

// 質問を送り、SSE のイベントを届いた順に onEvent へ渡す。履歴は送らない（サーバーが DB から読む）。
// EventSource は POST を送れないので、fetch の本文を読んで SSE を解く
export async function streamChat(
  message: string,
  sessionId: number | null,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await request('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  })
  if (!response.body) throw new ApiError('応答の本文がありません。', response.status)
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    // イベントは空行で区切られる
    let end: number
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      let name = ''
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) name = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (name && data) onEvent({ event: name, data: JSON.parse(data) } as ChatEvent)
    }
  }
}
