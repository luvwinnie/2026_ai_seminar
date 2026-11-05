import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
} from '@mui/material'
import { ApiError, getMasters, getReports, toApiError, type ReportList } from '../api'
import { SeverityChip, StatusChip } from '../components/Chips'
import PageHeader from '../components/PageHeader'
import { EmptyState, ErrorState, Loading } from '../components/StateViews'
import { CATEGORY_4M_LABELS, SEVERITY_LABELS, STATUS_LABELS, formatPercent } from '../labels'

const PER_PAGE_OPTIONS = [10, 25, 50]
const DEFAULT_PER_PAGE = 25
const DEFAULT_SORT = '-occurrence_date'
const SORT_OPTIONS = [
  { value: '-occurrence_date', label: '新しい順' },
  { value: 'occurrence_date', label: '古い順' },
  { value: '-total_cost', label: '損失額が大きい順' },
  { value: '-defect_count', label: '不良数が多い順' },
]
// 報告書ID・発生日・不良率と見出しは折り返さない（幅 1280px で表が収まるように、ほかの列は折り返す）
const NO_WRAP = { whiteSpace: 'nowrap' }
// URL クエリのうち、そのまま API に渡す条件
const FILTER_KEYS = ['q', 'status', 'severity', 'machine', 'process', 'category_4m', 'date_from', 'date_to']

type LoadState = { kind: 'loading' } | { kind: 'error'; error: ApiError } | { kind: 'ok'; data: ReportList }

interface SelectFilterProps {
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  allLabel?: string
  minWidth?: number
}

function SelectFilter({ label, value, options, onChange, allLabel = 'すべて', minWidth = 140 }: SelectFilterProps) {
  // URL に選択肢に無い値が書かれていても、その値を出せるようにする
  const items = value && !options.some((o) => o.value === value) ? [...options, { value, label: value }] : options
  return (
    <TextField
      select
      size="small"
      label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      sx={{ minWidth }}
      slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
    >
      {allLabel && <MenuItem value="">{allLabel}</MenuItem>}
      {items.map((o) => (
        <MenuItem key={o.value} value={o.value}>
          {o.label}
        </MenuItem>
      ))}
    </TextField>
  )
}

const codeOptions = (labels: Record<string, string>) =>
  Object.entries(labels).map(([value, label]) => ({ value, label }))

export default function ReportListPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()

  // 絞り込み・並べ替え・ページの状態は URL クエリに持つ
  const get = (key: string) => searchParams.get(key) ?? ''
  const qParam = get('q')
  const sort = get('sort') || DEFAULT_SORT
  const page = Math.max(1, Number(get('page')) || 1)
  const perPage = PER_PAGE_OPTIONS.includes(Number(get('per_page'))) ? Number(get('per_page')) : DEFAULT_PER_PAGE

  const apiQuery = new URLSearchParams()
  for (const key of FILTER_KEYS) if (get(key)) apiQuery.set(key, get(key))
  apiQuery.set('sort', sort)
  apiQuery.set('limit', String(perPage))
  apiQuery.set('offset', String((page - 1) * perPage))
  const apiQueryString = apiQuery.toString()

  // 条件を URL に書く。条件が変わったら1ページ目に戻す
  const updateParams = (changes: Record<string, string>, resetPage = true) => {
    // 今の URL から作る。setSearchParams の関数形は直前の描画の値を渡すため、
    // 描画の前に続けて変えると（開始日→終了日など）前の変更が消える
    const next = new URLSearchParams(window.location.search)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    if (resetPage) next.delete('page')
    setSearchParams(next)
  }

  // キーワードは入力が止まって 300ms たってから URL に書く
  const [keyword, setKeyword] = useState(qParam)
  const writtenQ = useRef(qParam)
  useEffect(() => {
    // 戻る・進むなどで URL の q が外から変わったときは、入力欄を合わせる
    if (qParam !== writtenQ.current) {
      writtenQ.current = qParam
      setKeyword(qParam)
    }
  }, [qParam])
  useEffect(() => {
    const value = keyword.trim()
    if (value === writtenQ.current) return
    const timer = setTimeout(() => {
      writtenQ.current = value
      updateParams({ q: value })
    }, 300)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword])

  // 一覧の読み込み
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState({ kind: 'loading' })
    getReports(apiQueryString, controller.signal)
      .then((data) => setState({ kind: 'ok', data }))
      .catch((error) => {
        if (!controller.signal.aborted) setState({ kind: 'error', error: toApiError(error) })
      })
    return () => controller.abort()
  }, [apiQueryString, reloadKey])

  // 機械・工程の選択肢はマスタから作る
  const [machines, setMachines] = useState<string[]>([])
  const [processes, setProcesses] = useState<string[]>([])
  const [mastersError, setMastersError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getMasters(controller.signal)
      .then((masters) => {
        setMachines(masters.machine.filter((m) => m.is_active).map((m) => m.name))
        setProcesses(masters.process.filter((m) => m.is_active).map((m) => m.name))
        setMastersError(null)
      })
      .catch((error) => {
        if (!controller.signal.aborted) setMastersError(toApiError(error).message)
      })
    return () => controller.abort()
  }, [reloadKey])

  const toOptions = (names: string[]) => names.map((name) => ({ value: name, label: name }))

  return (
    <>
      <PageHeader title="不適合報告書 一覧" />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack spacing={2}>
          <TextField
            size="small"
            fullWidth
            label="キーワード（報告書ID・部品名・部品番号・不具合内容）"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
          <Stack direction="row" spacing={1.5} useFlexGap sx={{ flexWrap: 'wrap' }}>
            <SelectFilter label="ステータス" value={get('status')} options={codeOptions(STATUS_LABELS)} onChange={(v) => updateParams({ status: v })} />
            <SelectFilter label="重要度" value={get('severity')} options={codeOptions(SEVERITY_LABELS)} onChange={(v) => updateParams({ severity: v })} />
            <SelectFilter label="機械" value={get('machine')} options={toOptions(machines)} onChange={(v) => updateParams({ machine: v })} minWidth={200} />
            <SelectFilter label="工程" value={get('process')} options={toOptions(processes)} onChange={(v) => updateParams({ process: v })} minWidth={160} />
            <SelectFilter label="4M" value={get('category_4m')} options={codeOptions(CATEGORY_4M_LABELS)} onChange={(v) => updateParams({ category_4m: v })} />
            <SelectFilter label="並び順" value={sort} options={SORT_OPTIONS} onChange={(v) => updateParams({ sort: v })} allLabel="" minWidth={180} />
          </Stack>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
            <TextField
              size="small"
              type="date"
              label="期間（開始日）"
              value={get('date_from')}
              onChange={(e) => updateParams({ date_from: e.target.value })}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'data-testid': 'date-from' } }}
            />
            <span>〜</span>
            <TextField
              size="small"
              type="date"
              label="期間（終了日）"
              value={get('date_to')}
              onChange={(e) => updateParams({ date_to: e.target.value })}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { 'data-testid': 'date-to' } }}
            />
          </Stack>
          {mastersError && <Alert severity="warning">機械・工程の選択肢を読み込めませんでした：{mastersError}</Alert>}
        </Stack>
      </Paper>

      {state.kind === 'loading' && <Loading />}

      {state.kind === 'error' &&
        (state.error.status === 422 ? (
          <ErrorState title="条件が正しくありません" message={state.error.message} />
        ) : (
          <ErrorState message={state.error.message} onRetry={() => setReloadKey((k) => k + 1)} />
        ))}

      {state.kind === 'ok' && (
        <Paper variant="outlined">
          <TableContainer>
            <Table size="small" data-testid="report-table" sx={{ '& th': NO_WRAP }}>
              <TableHead>
                <TableRow>
                  <TableCell>報告書ID</TableCell>
                  <TableCell>発生日</TableCell>
                  <TableCell>部品名</TableCell>
                  <TableCell>現象</TableCell>
                  <TableCell>機械</TableCell>
                  <TableCell>重要度</TableCell>
                  <TableCell>ステータス</TableCell>
                  <TableCell align="right">不良率</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {state.data.items.map((report) => (
                  <TableRow
                    key={report.defect_id}
                    hover
                    data-testid="report-row"
                    sx={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/reports/${report.defect_id}`, { state: { from: location.search } })}
                  >
                    <TableCell sx={NO_WRAP}>{report.defect_id}</TableCell>
                    <TableCell sx={NO_WRAP}>{report.occurrence_date}</TableCell>
                    <TableCell>{report.part_name}</TableCell>
                    <TableCell>{report.phenomenon}</TableCell>
                    <TableCell>{report.machine_name}</TableCell>
                    <TableCell>
                      <SeverityChip value={report.severity} />
                    </TableCell>
                    <TableCell>
                      <StatusChip value={report.status} />
                    </TableCell>
                    <TableCell align="right" sx={NO_WRAP}>
                      {formatPercent(report.defect_rate)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {state.data.total === 0 && <EmptyState />}
          <TablePagination
            component="div"
            data-testid="pagination"
            count={state.data.total}
            page={page - 1}
            rowsPerPage={perPage}
            rowsPerPageOptions={PER_PAGE_OPTIONS}
            labelRowsPerPage="表示件数"
            labelDisplayedRows={({ from, to, count }) => `${from}–${to}（全${count}件）`}
            onPageChange={(_, p) => updateParams({ page: p > 0 ? String(p + 1) : '' }, false)}
            onRowsPerPageChange={(e) => updateParams({ per_page: e.target.value })}
          />
        </Paper>
      )}
    </>
  )
}
