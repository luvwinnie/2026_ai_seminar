// API レスポンス型。docs/04_API設計書.md と docs/03_データモデル設計書.md のフィールド定義に一致させる。

export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type Status = 'open' | 'in_progress' | 'completed'
export type Category4M = 'Man' | 'Machine' | 'Material' | 'Method'

/** defect_reports テーブルの全カラム + 派生値 defect_rate */
export interface Report {
  id: number
  defect_id: string
  occurrence_date: string
  report_date?: string | null
  customer: string
  discoverer?: string | null
  process: string
  machine_name: string
  operator_name: string
  part_number: string
  part_name: string
  production_count: number
  defect_count: number
  defect_description: string
  good_condition?: string | null
  phenomenon: string
  cause?: string | null
  factor?: string | null
  category_4m?: Category4M | string | null
  severity: Severity
  status: Status
  countermeasure?: string | null
  material_cost?: number | null
  processing_cost?: number | null
  outsourcing_cost?: number | null
  other_cost?: number | null
  total_cost?: number | null
  is_recurrence?: boolean
  has_procedure?: boolean
  notes?: string | null
  ai_improvement?: string | null
  created_at: string
  updated_at?: string | null
  defect_rate: number | null
}

/** POST/PUT で送る Report フィールドのサブセット(id / created_at 等はサーバ付与) */
export type ReportInput = Partial<Omit<Report, 'id' | 'created_at' | 'updated_at' | 'defect_rate'>>

export interface ReportListResponse {
  total: number
  items: Report[]
}

export interface ReportListParams {
  q?: string
  status?: string
  severity?: string
  machine?: string
  process?: string
  category_4m?: string
  date_from?: string
  date_to?: string
  limit?: number
  offset?: number
  sort?: string
}

// --- ダッシュボード統計 ---

export interface Kpi {
  total_reports: number
  total_defects: number
  total_production: number
  defect_rate: number
  fpy: number
  total_cost: number
  recurrence_rate: number
  open_count: number
}

export interface MonthlyTrendPoint {
  month: string
  reports: number
  defects: number
  production: number
  defect_rate: number
}

export interface ParetoPoint {
  name: string
  count: number
  ratio: number
  cumulative_ratio: number
}

export interface BreakdownRow {
  name: string
  reports: number
  defects: number
  defect_rate: number
  total_cost: number
}

export interface NameCount {
  name: string
  count: number
}

export interface DashboardStatistics {
  kpi: Kpi
  monthly_trend: MonthlyTrendPoint[]
  pareto_phenomenon: ParetoPoint[]
  by_machine: BreakdownRow[]
  by_operator: BreakdownRow[]
  by_process: BreakdownRow[]
  by_customer: BreakdownRow[]
  by_4m: NameCount[]
  by_severity: NameCount[]
}

export interface ControlChartPoint {
  period: string
  n: number
  defects: number
  p: number
  ucl: number
  lcl: number
}

export interface ControlChartResponse {
  items: ControlChartPoint[]
  p_bar: number
}

// --- 分析・アラート ---

export interface AlertItem {
  level: 'critical' | 'warning' | 'info'
  title: string
  message: string
  related?: {
    machine?: string
    phenomenon?: string
  }
}

export interface AlertsResponse {
  items: AlertItem[]
}

export interface FourMAnalysisResult {
  category_4m: string
  factor: string
  reasoning: string
  improvements: string[]
}

// --- 帳票取り込み ---

export interface IngestUploadResponse {
  extracted: ReportInput
  confidence: 'high' | 'medium' | 'low'
  warnings: string[]
  source_filename: string
}

// --- チャット ---

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatSource {
  defect_id: string
  part_name: string
  phenomenon: string
  snippet: string
  score: number
}

// --- ヘルスチェック ---

export interface HealthResponse {
  status: string
  reports: number
  anthropic_configured: boolean
  vector_search: 'e5' | 'keyword'
}
