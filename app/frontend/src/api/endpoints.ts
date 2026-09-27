import { client } from './client'
import type {
  SmartSearchResponse,
  SimilarReportsResponse,
  WeeklyDigest,
  CapaAction,
  CapaDraftResponse,
  EightDReport,
  ReportPhoto,
  PhotoAnalysis,
  Report,
  ReportInput,
  ReportListParams,
  ReportListResponse,
  DashboardStatistics,
  ControlChartResponse,
  AlertsResponse,
  FourMAnalysisResult,
  IngestUploadResponse,
  HealthResponse,
  MasterCategory,
  MasterItem,
  MastersByCategory,
  MasterUpdateResult,
  ChatSession,
  ChatSessionDetail,
  GraphResponse,
} from '../types'
import type { TriagePreview, TriagePreviewInput, TriageRun, TriageStatus } from '../types'
import { MASTER_CATEGORIES } from '../constants/masters'

// --- 報告書 CRUD ---

export async function fetchReports(params: ReportListParams): Promise<ReportListResponse> {
  const { data } = await client.get<ReportListResponse>('/api/reports', { params })
  return data
}

export async function smartSearchReports(params: {
  q: string
  top_k?: number
  machine?: string
  process?: string
}): Promise<SmartSearchResponse> {
  const { data } = await client.get<SmartSearchResponse>('/api/reports/search', { params })
  return data
}

export async function fetchReport(defectId: string): Promise<Report> {
  const { data } = await client.get<Report>(`/api/reports/${defectId}`)
  return data
}

export async function createReport(payload: ReportInput): Promise<Report> {
  const { data } = await client.post<Report>('/api/reports', payload)
  return data
}

export async function updateReport(defectId: string, payload: ReportInput): Promise<Report> {
  const { data } = await client.put<Report>(`/api/reports/${defectId}`, payload)
  return data
}

export async function deleteReport(defectId: string): Promise<void> {
  await client.delete(`/api/reports/${defectId}`)
}

// --- ダッシュボード ---

export async function fetchStatistics(params?: {
  date_from?: string
  date_to?: string
}): Promise<DashboardStatistics> {
  const { data } = await client.get<DashboardStatistics>('/api/dashboard/statistics', { params })
  return data
}

export async function fetchControlChart(months = 12): Promise<ControlChartResponse> {
  const { data } = await client.get<ControlChartResponse>('/api/dashboard/control-chart', {
    params: { months },
  })
  return data
}

// --- 分析・AI ---

export async function fetchAlerts(): Promise<AlertsResponse> {
  const { data } = await client.get<AlertsResponse>('/api/analysis/alerts')
  return data
}

export async function analyze4M(defectId: string): Promise<FourMAnalysisResult> {
  const { data } = await client.post<FourMAnalysisResult>(`/api/analysis/4m/${defectId}`)
  return data
}

// --- 帳票取り込み ---

export async function ingestUpload(file: File): Promise<IngestUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post<IngestUploadResponse>('/api/ingest/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function ingestConfirm(payload: ReportInput): Promise<Report> {
  const { data } = await client.post<Report>('/api/ingest/confirm', payload)
  return data
}

// --- ヘルスチェック ---

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/health')
  return data
}

// --- マスタ管理(docs/04 §2.5)---
// バックエンドは {"items": [...]} 形式(グルーピング可)。フロントは常に
// カテゴリ別 Record に正規化してから扱う(サーバ実装差に強くするため両形式を許容)。

function emptyMasters(): MastersByCategory {
  return MASTER_CATEGORIES.reduce((acc, c) => {
    acc[c] = []
    return acc
  }, {} as MastersByCategory)
}

/** GET /api/masters → 全カテゴリのマスタ(カテゴリ別に正規化) */
export async function fetchMasters(): Promise<MastersByCategory> {
  const { data } = await client.get<unknown>('/api/masters')
  const grouped = emptyMasters()

  // 形式A: { customer: [...], process: [...], ... }
  // 形式B: { items: [ {category, ...}, ... ] }
  const record = data as Record<string, unknown>
  const items = (record?.items as MasterItem[] | undefined) ?? null
  if (Array.isArray(items)) {
    for (const it of items) {
      const cat = it.category as MasterCategory
      if (grouped[cat]) grouped[cat].push(it)
    }
  } else if (record && typeof record === 'object') {
    for (const cat of MASTER_CATEGORIES) {
      const arr = record[cat]
      if (Array.isArray(arr)) grouped[cat] = arr as MasterItem[]
    }
  }
  return grouped
}

/** GET /api/masters/{category}?active_only= → 指定カテゴリの一覧 */
export async function fetchMasterCategory(
  category: MasterCategory,
  activeOnly = false,
): Promise<MasterItem[]> {
  const { data } = await client.get<{ items?: MasterItem[] } | MasterItem[]>(
    `/api/masters/${category}`,
    { params: activeOnly ? { active_only: true } : undefined },
  )
  if (Array.isArray(data)) return data
  return data.items ?? []
}

/** POST /api/masters/{category} body {name} → 新規登録(重複は 409) */
export async function createMaster(category: MasterCategory, name: string): Promise<MasterItem> {
  const { data } = await client.post<MasterItem>(`/api/masters/${category}`, { name })
  return data
}

/** PUT /api/masters/{category}/{id} → 更新(リネームは既存報告書へ伝播、件数を返す) */
export async function updateMaster(
  category: MasterCategory,
  id: number,
  patch: { name?: string; is_active?: boolean },
): Promise<MasterUpdateResult> {
  const { data } = await client.put<MasterUpdateResult>(`/api/masters/${category}/${id}`, patch)
  return data
}

/** DELETE /api/masters/{category}/{id} → 削除(使用中は 409) */
export async function deleteMaster(category: MasterCategory, id: number): Promise<void> {
  await client.delete(`/api/masters/${category}/${id}`)
}

// --- チャットセッション(履歴)---

/** GET /api/chat/sessions → セッション一覧(更新降順) */
export async function fetchChatSessions(): Promise<ChatSession[]> {
  const { data } = await client.get<ChatSession[] | { items?: ChatSession[] }>('/api/chat/sessions')
  return Array.isArray(data) ? data : (data.items ?? [])
}

/** GET /api/chat/sessions/{id} → セッション詳細(メッセージ含む) */
export async function fetchChatSession(id: number): Promise<ChatSessionDetail> {
  const { data } = await client.get<ChatSessionDetail>(`/api/chat/sessions/${id}`)
  return data
}

/** DELETE /api/chat/sessions/{id} → 削除 */
export async function deleteChatSession(id: number): Promise<void> {
  await client.delete(`/api/chat/sessions/${id}`)
}


// --- 類似事例サジェスト(docs/10 A-1) ---
export async function fetchSimilarReports(defectId: string, topK = 3): Promise<SimilarReportsResponse> {
  const { data } = await client.get<SimilarReportsResponse>(`/api/reports/${defectId}/similar`, {
    params: { top_k: topK },
  })
  return data
}

// --- 週次ダイジェスト(docs/10 A-2) ---
export async function fetchDigests(): Promise<{ items: WeeklyDigest[] }> {
  const { data } = await client.get('/api/digests')
  return data
}

export async function generateDigest(days = 7): Promise<WeeklyDigest> {
  const { data } = await client.post(`/api/digests/generate?days=${days}`)
  return data
}

// --- CAPA・8D(docs/10 A-3) ---
export async function fetchCapaList(params?: {
  status?: string
  defect_id?: string
  overdue?: boolean
}): Promise<{ total: number; items: CapaAction[] }> {
  const { data } = await client.get('/api/capa', { params })
  return data
}

export async function createCapa(body: {
  defect_id: string
  title: string
  action_type?: string
  description?: string
  owner?: string
  due_date?: string
}): Promise<CapaAction> {
  const { data } = await client.post('/api/capa', body)
  return data
}

export async function updateCapa(capaId: string, patch: Partial<CapaAction>): Promise<CapaAction> {
  const { data } = await client.put(`/api/capa/${capaId}`, patch)
  return data
}

export async function draftCapa(defectId: string): Promise<CapaDraftResponse> {
  const { data } = await client.post(`/api/capa/draft/${defectId}`)
  return data
}

export async function generateEightD(defectId: string): Promise<EightDReport> {
  const { data } = await client.post(`/api/capa/eight_d/${defectId}`)
  return data
}

export async function fetchEightD(defectId: string): Promise<{ items: EightDReport[] }> {
  const { data } = await client.get(`/api/capa/eight_d/${defectId}`)
  return data
}

// --- 現場写真(docs/10 B-4) ---
export async function fetchPhotos(defectId: string): Promise<{ items: ReportPhoto[] }> {
  const { data } = await client.get(`/api/reports/${defectId}/photos`)
  return data
}

export async function uploadPhoto(defectId: string, file: File): Promise<ReportPhoto> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post(`/api/reports/${defectId}/photos`, form)
  return data
}

export async function deletePhoto(defectId: string, name: string): Promise<void> {
  await client.delete(`/api/reports/${defectId}/photos/${name}`)
}

export async function analyzePhoto(defectId: string, name: string): Promise<PhotoAnalysis> {
  const { data } = await client.post(`/api/reports/${defectId}/photos/${name}/analyze`)
  return data
}

// --- 関連マップ(GraphRAG層) ---
export async function fetchGraph(): Promise<GraphResponse> {
  const { data } = await client.get<GraphResponse>('/api/graph')
  return data
}

// --- チャット回答フィードバック ---
export async function sendChatFeedback(body: {
  session_id?: number | null
  message_index?: number | null
  trace_id?: string
  rating: 1 | -1
  comment?: string
  answer_excerpt?: string
  question_excerpt?: string
}): Promise<void> {
  await client.post('/api/chat/feedback', body)
}

// ---- 報告書トリアージ(判断モデル Jev + LangGraph)----
export async function fetchTriageStatus(): Promise<TriageStatus> {
  const { data } = await client.get<TriageStatus>('/api/triage/status')
  return data
}

export async function previewTriage(payload: TriagePreviewInput): Promise<TriagePreview> {
  const { data } = await client.post<TriagePreview>('/api/triage/preview', payload)
  return data
}

export async function runTriage(defectId: string): Promise<TriageRun> {
  const { data } = await client.post<TriageRun>(`/api/triage/reports/${defectId}`)
  return data
}

/** 最新の判定。まだ判定していなければ null。 */
export async function fetchTriage(defectId: string): Promise<TriageRun | null> {
  try {
    const { data } = await client.get<TriageRun>(`/api/triage/reports/${defectId}`)
    return data
  } catch (e: unknown) {
    if ((e as { response?: { status?: number } }).response?.status === 404) return null
    throw e
  }
}

export async function resumeTriage(
  runId: string,
  body: { approved: boolean; selected: number[]; note?: string },
): Promise<TriageRun> {
  const { data } = await client.post<TriageRun>(`/api/triage/runs/${runId}/resume`, body)
  return data
}
