import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import SaveIcon from '@mui/icons-material/Save'
import CloseIcon from '@mui/icons-material/Close'
import PsychologyIcon from '@mui/icons-material/Psychology'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import PageHeader from '../components/PageHeader'
import ReportForm from '../components/ReportForm'
import { SeverityChip, StatusChip } from '../components/Chips'
import { Loading, ErrorState } from '../components/StateViews'
import { analyze4M, deleteReport, fetchReport, updateReport } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { FourMAnalysisResult, Report, ReportInput, Severity, Status } from '../types'
import { CATEGORY_4M_LABELS } from '../constants/vocab'
import { formatCurrency, formatDate, formatNumber, formatPercent } from '../utils/format'

/** Report から編集可能なフィールドのみを抽出して ReportInput にする */
function toReportInput(r: Report): ReportInput {
  return {
    defect_id: r.defect_id,
    occurrence_date: r.occurrence_date,
    report_date: r.report_date,
    customer: r.customer,
    discoverer: r.discoverer,
    process: r.process,
    machine_name: r.machine_name,
    operator_name: r.operator_name,
    part_number: r.part_number,
    part_name: r.part_name,
    production_count: r.production_count,
    defect_count: r.defect_count,
    defect_description: r.defect_description,
    good_condition: r.good_condition,
    phenomenon: r.phenomenon,
    cause: r.cause,
    factor: r.factor,
    category_4m: r.category_4m,
    severity: r.severity,
    status: r.status,
    countermeasure: r.countermeasure,
    material_cost: r.material_cost,
    processing_cost: r.processing_cost,
    outsourcing_cost: r.outsourcing_cost,
    other_cost: r.other_cost,
    total_cost: r.total_cost,
    is_recurrence: r.is_recurrence,
    has_procedure: r.has_procedure,
    notes: r.notes,
  }
}

/** 読み取り専用のフィールド行 */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ py: 1, borderBottom: '1px solid #f1f5f9' }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
        {label}
      </Typography>
      <Typography sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{children ?? '—'}</Typography>
    </Box>
  )
}

/** 表示用セクションカード */
function ViewSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1, color: 'primary.main' }}>
          {title}
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: { xs: 0, sm: 2 } }}>
          {children}
        </Box>
      </CardContent>
    </Card>
  )
}

export default function ReportDetail() {
  const { defectId } = useParams<{ defectId: string }>()
  const navigate = useNavigate()

  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<ReportInput>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<FourMAnalysisResult | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  const load = useCallback(() => {
    if (!defectId) return
    setLoading(true)
    setError(null)
    fetchReport(defectId)
      .then(setReport)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false))
  }, [defectId])

  useEffect(() => {
    load()
  }, [load])

  const startEdit = () => {
    if (!report) return
    setDraft(toReportInput(report))
    setSaveError(null)
    setEditing(true)
  }

  const handleSave = async () => {
    if (!defectId) return
    setSaving(true)
    setSaveError(null)
    try {
      const updated = await updateReport(defectId, draft)
      setReport(updated)
      setEditing(false)
    } catch (e) {
      setSaveError(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!defectId) return
    setDeleting(true)
    try {
      await deleteReport(defectId)
      navigate('/reports')
    } catch (e) {
      setSaveError(errorMessage(e))
      setDeleting(false)
      setConfirmOpen(false)
    }
  }

  const handleAnalyze = async () => {
    if (!defectId) return
    setAnalyzing(true)
    setAnalysisError(null)
    try {
      const result = await analyze4M(defectId)
      setAnalysis(result)
      load() // category_4m / factor / ai_improvement が更新されるので再取得
    } catch (e) {
      setAnalysisError(errorMessage(e))
    } finally {
      setAnalyzing(false)
    }
  }

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} />
  if (!report) return null

  return (
    <Box>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/reports')} sx={{ mb: 1 }}>
        一覧へ戻る
      </Button>

      <PageHeader
        title={report.defect_id}
        subtitle={`${report.part_name} · ${report.phenomenon}`}
        action={
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            {!editing && (
              <>
                <Button
                  variant="contained"
                  color="secondary"
                  startIcon={<PsychologyIcon />}
                  onClick={handleAnalyze}
                  disabled={analyzing}
                >
                  {analyzing ? 'AI分析中…' : 'AIで4M分析'}
                </Button>
                <Button variant="outlined" startIcon={<EditIcon />} onClick={startEdit}>
                  編集
                </Button>
                <Button variant="outlined" color="error" startIcon={<DeleteIcon />} onClick={() => setConfirmOpen(true)}>
                  削除
                </Button>
              </>
            )}
            {editing && (
              <>
                <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
                  {saving ? '保存中…' : '保存'}
                </Button>
                <Button variant="text" startIcon={<CloseIcon />} onClick={() => setEditing(false)} disabled={saving}>
                  キャンセル
                </Button>
              </>
            )}
          </Stack>
        }
      />

      {saveError && <ErrorState message={saveError} />}
      {analysisError && <ErrorState message={analysisError} />}

      {analysis && !editing && (
        <Alert severity="success" icon={<PsychologyIcon />} sx={{ mb: 2 }} onClose={() => setAnalysis(null)}>
          <Typography sx={{ fontWeight: 700 }}>
            AI 4M分析: {CATEGORY_4M_LABELS[analysis.category_4m] ?? analysis.category_4m} / 要因: {analysis.factor}
          </Typography>
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            {analysis.reasoning}
          </Typography>
          {analysis.improvements.length > 0 && (
            <List dense sx={{ mt: 0.5 }}>
              {analysis.improvements.map((imp, i) => (
                <ListItem key={i} sx={{ py: 0, display: 'list-item', listStyleType: 'disc', ml: 3 }}>
                  <ListItemText primary={imp} />
                </ListItem>
              ))}
            </List>
          )}
        </Alert>
      )}

      {editing ? (
        <Card>
          <CardContent>
            {saving && (
              <Alert severity="info" sx={{ mb: 2 }}>
                保存中です…
              </Alert>
            )}
            <ReportForm value={draft} onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))} />
          </CardContent>
        </Card>
      ) : (
        <>
          <ViewSection title="基本情報">
            <Field label="報告書ID">{report.defect_id}</Field>
            <Field label="客先">{report.customer}</Field>
            <Field label="発生日">{formatDate(report.occurrence_date)}</Field>
            <Field label="報告日">{formatDate(report.report_date)}</Field>
            <Field label="発見者名">{report.discoverer}</Field>
            <Field label="部品番号">{report.part_number}</Field>
            <Field label="部品名称">{report.part_name}</Field>
          </ViewSection>

          <ViewSection title="不具合内容">
            <Field label="発生工程">{report.process}</Field>
            <Field label="使用機械">{report.machine_name}</Field>
            <Field label="作業者名">{report.operator_name}</Field>
            <Field label="現象分類">{report.phenomenon}</Field>
            <Field label="加工数">{formatNumber(report.production_count)}</Field>
            <Field label="不適合数">{formatNumber(report.defect_count)}</Field>
            <Field label="不良率">{formatPercent(report.defect_rate, 2)}</Field>
            <Field label="重要度">
              <SeverityChip severity={report.severity as Severity} />
            </Field>
            <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
              <Field label="不具合内容">{report.defect_description}</Field>
            </Box>
            <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
              <Field label="良品状態">{report.good_condition}</Field>
            </Box>
          </ViewSection>

          <ViewSection title="原因・4M分析">
            <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
              <Field label="原因">{report.cause}</Field>
            </Box>
            <Field label="要因">{report.factor}</Field>
            <Field label="4M分類">
              {report.category_4m ? CATEGORY_4M_LABELS[report.category_4m] ?? report.category_4m : '未分類'}
            </Field>
            <Field label="再発案件">{report.is_recurrence ? 'はい' : 'いいえ'}</Field>
            <Field label="手順書">{report.has_procedure ? 'あり' : 'なし'}</Field>
            {report.ai_improvement && (
              <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
                <Field label="AI改善提案">{report.ai_improvement}</Field>
              </Box>
            )}
          </ViewSection>

          <ViewSection title="対策">
            <Field label="ステータス">
              <StatusChip status={report.status as Status} />
            </Field>
            <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
              <Field label="対策">{report.countermeasure}</Field>
            </Box>
            <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
              <Field label="備考">{report.notes}</Field>
            </Box>
          </ViewSection>

          <ViewSection title="費用">
            <Field label="材料費">{formatCurrency(report.material_cost)}</Field>
            <Field label="社内加工費">{formatCurrency(report.processing_cost)}</Field>
            <Field label="外注加工費">{formatCurrency(report.outsourcing_cost)}</Field>
            <Field label="その他費用">{formatCurrency(report.other_cost)}</Field>
            <Box sx={{ gridColumn: { xs: '1', sm: '1 / -1' } }}>
              <Divider sx={{ my: 1 }} />
              <Typography sx={{ fontWeight: 700 }}>
                合計損失: {formatCurrency(report.total_cost)}
              </Typography>
            </Box>
          </ViewSection>
        </>
      )}

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>報告書を削除しますか?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {report.defect_id}({report.part_name})を削除します。この操作は取り消せません。
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)} disabled={deleting}>
            キャンセル
          </Button>
          <Button color="error" variant="contained" onClick={handleDelete} disabled={deleting}>
            {deleting ? '削除中…' : '削除する'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
