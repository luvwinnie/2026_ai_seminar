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
  customer?: string
  operator?: string
  phenomenon?: string
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

// MCPツールの状態遷移(SSE event: tool)
export interface ChatToolEvent {
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  title: string | null
}

// チャットセッション(履歴)
export interface ChatSession {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

// セッション詳細の1メッセージ
export interface ChatSessionMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources: ChatSource[] | null
  tools: ChatToolEvent[] | null
  thinking: string | null
  created_at: string
}

export interface ChatSessionDetail {
  session: ChatSession
  messages: ChatSessionMessage[]
}

// SSE の先頭で届くセッション確定イベント(event: session)
export interface ChatSessionEvent {
  id: number
  title: string
}

// --- ヘルスチェック ---

export interface HealthResponse {
  status: string
  reports: number
  anthropic_configured: boolean
  vector_search: 'e5' | 'keyword'
  // チャットのバックエンド種別(新レスポンス)。旧レスポンスでは欠落するため任意。
  chat_backend?: 'opencode' | 'anthropic' | 'none'
}

// --- マスタ管理(docs/04 §2.5, docs/03 §2.5)---

// ドロップダウン選択肢のマスタ対象6カテゴリ。severity/status/category_4m は固定列挙のため対象外。
export type MasterCategory =
  | 'customer'
  | 'process'
  | 'machine'
  | 'operator'
  | 'phenomenon'
  | 'factor'

export interface MasterItem {
  id: number
  category: MasterCategory | string
  name: string
  sort_order: number
  is_active: boolean
  usage_count: number
  created_at?: string
}

// 全カテゴリのマスタをカテゴリ別にまとめたもの
export type MastersByCategory = Record<MasterCategory, MasterItem[]>

// PUT のレスポンス: 更新後 Master + リネーム伝播した報告書件数
export interface MasterUpdateResult extends MasterItem {
  updated_reports: number
}


// --- スマート検索(意味検索) ---
export interface SmartSearchResult {
  defect_id: string
  part_name: string | null
  machine_name: string | null
  process: string | null
  phenomenon: string | null
  snippet: string
  score: number
  search_mode: string
}

export interface SmartSearchResponse {
  items: SmartSearchResult[]
  search_mode: string
}


// --- 類似事例(docs/10 A-1) ---
export interface SimilarReport {
  defect_id: string
  occurrence_date: string | null
  part_name: string | null
  machine_name: string | null
  process: string | null
  phenomenon: string | null
  cause: string
  countermeasure: string
  score: number
}

export interface SimilarReportsResponse {
  defect_id: string
  items: SimilarReport[]
}

// --- 週次ダイジェスト(docs/10 A-2) ---
export interface WeeklyDigest {
  id: number
  period_start: string
  period_end: string
  content_md: string
  ai_backend: string | null
  created_at: string | null
}

// --- CAPA・8D(docs/10 A-3) ---
export interface CapaAction {
  capa_id: string
  defect_id: string
  action_type: string
  title: string
  description: string | null
  owner: string | null
  due_date: string | null
  status: string
  effect_note: string | null
  overdue: boolean
  created_at: string | null
  updated_at: string | null
}

export interface CapaDraftItem {
  action_type: string
  title: string
  description: string
  based_on?: string
}

export interface CapaDraftResponse {
  defect_id: string
  actions: CapaDraftItem[]
  ai_backend: string
}

export interface EightDReport {
  id: number
  defect_id?: string
  content_md: string
  ai_backend: string | null
  created_at: string
}

// --- 現場写真(docs/10 B-4) ---
export interface ReportPhoto {
  name: string
  url: string
  size: number
}

export interface PhotoAnalysis {
  name: string
  observation?: string
  phenomenon_candidates?: string[]
  notes?: string
}

// --- 関連マップ ---
export interface GraphNode {
  id: string
  part: string
  phenomenon: string
  machine: string
  severity: string
  cost: number
  d: number
}

export interface GraphLink {
  s: string
  t: string
  w: number
  m: boolean
}

export interface GraphResponse {
  mode: 'embedding' | 'jaccard'
  nodes: GraphNode[]
  links: GraphLink[]
}

// ---- 報告書トリアージ(判断モデル Jev + LangGraph)----
export interface TriageCandidate {
  value: string
  p: number
}
export interface TriageChoiceDecision {
  value: string | null
  confidence: number
  p_top?: number // 1位の確率
  margin?: number // 1位と2位の確率の差(採否はこれと p_top で決める)
  top: TriageCandidate[]
  accepted: boolean
  source: 'jev' | 'llm' | 'rule'
  reason?: string
  rule_agrees_with_jev?: boolean
  jev_value?: string | null
  jev_confidence?: number
}
export interface TriageSeverityDecision {
  value: Severity
  score: number
  confidence: number
  p_top?: number
  margin?: number
  top: TriageCandidate[]
  accepted: boolean
  source: 'jev'
}
export interface TriageFlagDecision {
  value: boolean
  probability: number
  accepted: boolean
  source: 'jev' | 'rule'
}
export interface TriageDecisions {
  phenomenon?: TriageChoiceDecision
  factor?: TriageChoiceDecision
  category_4m?: TriageChoiceDecision
  severity?: TriageSeverityDecision
  systemic?: TriageFlagDecision
  outflow?: TriageFlagDecision
  info_missing?: TriageFlagDecision
}
export interface TriageJevMeta {
  model: string
  measured_model?: string | null // 閾値を測ったときの版
  model_matches_thresholds?: boolean
  criteria_hash?: string
  cached?: boolean
  calls: number
  latency_ms: number
  input_tokens: number
  cost_usd: number
  request_ids: (string | null)[]
  notes?: string[] // 自動で採らなかった理由(版の違い・記述不足など)
}
export interface TriageCapaAction {
  action_type: string
  title: string
  description?: string
  based_on?: string
  jev_fits_cause?: number
  jev_checks?: { cause: number; recurrence: number; concrete: number } // Jev の3つの確かめ
  jev_ok?: boolean // 3つとも 0.7 以上
}
export type TriageRunStatus = 'completed' | 'waiting_approval' | 'approved' | 'rejected'
export interface TriageRun {
  run_id: string
  defect_id: string
  status: TriageRunStatus
  created_at?: string | null
  decisions: TriageDecisions
  jev: TriageJevMeta
  llm: { fields: string[]; backend: string | null; result?: Record<string, string | null>; error?: string } | null
  conflicts: { field: 'phenomenon' | 'factor' | 'category_4m'; registered: string; suggested: string; confidence: number }[] | null
  escalation: { needed: boolean; reasons: string[]; existing_capa: number } | null
  capa_draft: { actions: TriageCapaAction[]; ai_backend: string | null; similar: string[] } | null
  review: { approved: boolean; selected: number[]; note?: string | null } | null
  created_capa: string[] | null
  route: string[]
}
export interface TriageStatus {
  enabled: boolean
  backend: string
  model: string | null
  thresholds: Record<string, number>
  ledger: { calls: number; errors: number; input_tokens: number; cost_usd: number; avg_latency_ms: number | null }
}
export interface TriagePreviewInput {
  defect_description: string
  cause?: string | null
  countermeasure?: string | null
  process?: string | null
  machine_name?: string | null
  part_name?: string | null
}
export interface TriagePreview {
  decisions: TriageDecisions
  jev: TriageJevMeta
}
