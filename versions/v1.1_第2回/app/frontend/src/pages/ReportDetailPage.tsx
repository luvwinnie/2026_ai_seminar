import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Box, Button, Paper, Stack, Typography } from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { ApiError, getReport, toApiError, type Report } from '../api'
import { SeverityChip, StatusChip } from '../components/Chips'
import PageHeader from '../components/PageHeader'
import { ErrorState, Loading } from '../components/StateViews'
import { format4M, formatPercent, formatYen, show } from '../labels'

type LoadState = { kind: 'loading' } | { kind: 'error'; error: ApiError } | { kind: 'ok'; report: Report }

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 700 }}>
        {title}
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 4, rowGap: 1.25 }}>{children}</Box>
    </Paper>
  )
}

// ラベルと値。full は2列ぶんを使う（長い文章）
function Field({ label, children, full = false }: { label: string; children: ReactNode; full?: boolean }) {
  return (
    <Stack direction="row" spacing={2} sx={{ gridColumn: full ? '1 / -1' : undefined }}>
      <Typography color="text.secondary" sx={{ minWidth: 96, flexShrink: 0 }}>
        {label}
      </Typography>
      <Box data-testid={`field-${label}`} sx={{ whiteSpace: 'pre-wrap' }}>
        {children}
      </Box>
    </Stack>
  )
}

const yesNo = (value: boolean | null, yes: string, no: string) => (value === null ? '—' : value ? yes : no)

export default function ReportDetailPage() {
  const { defectId = '' } = useParams()
  const location = useLocation()
  // 一覧から来たときは、同じ条件の一覧へ戻る
  const backTo = `/reports${(location.state as { from?: string } | null)?.from ?? ''}`

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    setState({ kind: 'loading' })
    getReport(defectId, controller.signal)
      .then((report) => setState({ kind: 'ok', report }))
      .catch((error) => {
        if (!controller.signal.aborted) setState({ kind: 'error', error: toApiError(error) })
      })
    return () => controller.abort()
  }, [defectId])

  const backButton = (
    <Button component={Link} to={backTo} startIcon={<ArrowBackIcon />} sx={{ mb: 1 }}>
      一覧へ戻る
    </Button>
  )

  if (state.kind === 'loading') return <>{backButton}<Loading /></>
  // 詳細は、失敗したら原因だけを出す
  if (state.kind === 'error') return <>{backButton}<ErrorState message={state.error.message} /></>

  const r = state.report
  return (
    <>
      {backButton}
      <PageHeader title={r.defect_id} subtitle={`${r.part_name} · ${r.phenomenon}`} />

      <Section title="基本情報">
        <Field label="報告書ID">{r.defect_id}</Field>
        <Field label="客先">{show(r.customer)}</Field>
        <Field label="発生日">{show(r.occurrence_date)}</Field>
        <Field label="報告日">{show(r.report_date)}</Field>
        <Field label="発見者名">{show(r.discoverer)}</Field>
        <Field label="部品番号">{show(r.part_number)}</Field>
        <Field label="部品名称">{show(r.part_name)}</Field>
      </Section>

      <Section title="不具合内容">
        <Field label="発生工程">{show(r.process)}</Field>
        <Field label="使用機械">{show(r.machine_name)}</Field>
        <Field label="作業者名">{show(r.operator_name)}</Field>
        <Field label="現象分類">{show(r.phenomenon)}</Field>
        <Field label="加工数">{show(r.production_count)}</Field>
        <Field label="不適合数">{show(r.defect_count)}</Field>
        <Field label="不良率">{formatPercent(r.defect_rate)}</Field>
        <Field label="重要度">
          <SeverityChip value={r.severity} />
        </Field>
        <Field label="不具合内容" full>{show(r.defect_description)}</Field>
        <Field label="良品状態" full>{show(r.good_condition)}</Field>
      </Section>

      <Section title="原因・4M分析">
        <Field label="原因" full>{show(r.cause)}</Field>
        <Field label="要因">{show(r.factor)}</Field>
        <Field label="4M分類">{format4M(r.category_4m)}</Field>
        <Field label="再発案件">{yesNo(r.is_recurrence, 'はい', 'いいえ')}</Field>
        <Field label="手順書">{yesNo(r.has_procedure, 'あり', 'なし')}</Field>
      </Section>

      <Section title="対策">
        <Field label="ステータス" full>
          <StatusChip value={r.status} />
        </Field>
        <Field label="対策" full>{show(r.countermeasure)}</Field>
        <Field label="備考" full>{show(r.notes)}</Field>
      </Section>

      <Section title="費用">
        <Field label="材料費">{formatYen(r.material_cost)}</Field>
        <Field label="社内加工費">{formatYen(r.processing_cost)}</Field>
        <Field label="外注加工費">{formatYen(r.outsourcing_cost)}</Field>
        <Field label="その他費用">{formatYen(r.other_cost)}</Field>
        <Field label="合計損失" full>
          <Typography sx={{ fontWeight: 700 }}>{formatYen(r.total_cost)}</Typography>
        </Field>
      </Section>
    </>
  )
}
