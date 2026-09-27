import { client } from './client'
import type {
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
} from '../types'

// --- 報告書 CRUD ---

export async function fetchReports(params: ReportListParams): Promise<ReportListResponse> {
  const { data } = await client.get<ReportListResponse>('/api/reports', { params })
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
