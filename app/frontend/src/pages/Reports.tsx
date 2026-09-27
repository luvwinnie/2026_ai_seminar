/**
 * 報告書 一覧・検索 — 全フィルタ+スマート検索(意味検索)。
 *
 * フィルタ状態の正本は URL クエリ(人間のUI操作と AI の ui_navigate が同じ場所を書く)。
 *   q / status / severity / machine / process / customer / operator / phenomenon /
 *   category_4m / sort / date_from / date_to / mode(=smart で意味検索)
 * キーワードモード: /api/reports(完全一致フィルタ+LIKE検索)
 * スマートモード  : /api/reports/search(ハイブリッド意味検索。機械・工程のみ後段絞り込み)
 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Box,
  Button,
  Card,
  Chip,
  MenuItem,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import PageHeader from '../components/PageHeader'
import PeriodFilter from '../components/PeriodFilter'
import { SeverityChip, StatusChip } from '../components/Chips'
import { Loading, ErrorState, EmptyState } from '../components/StateViews'
import { fetchReports, smartSearchReports } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { Report, Severity, SmartSearchResult, Status } from '../types'
import {
  CATEGORY_4M_LABELS,
  SEVERITIES,
  SEVERITY_LABELS,
  STATUSES,
  STATUS_LABELS,
} from '../constants/vocab'
import { useMasters } from '../hooks/useMasters'
import { formatDate, formatPercent } from '../utils/format'

const CATEGORY_4M = ['Man', 'Machine', 'Material', 'Method']
const SORT_OPTIONS: [string, string][] = [
  ['-occurrence_date', '新しい順'],
  ['occurrence_date', '古い順'],
  ['-total_cost', '損失額が大きい順'],
  ['-defect_count', '不良数が多い順'],
]

export default function Reports() {
  const navigate = useNavigate()
  // フィルタ状態の正本 = URLクエリ(AIの ui_navigate とUI操作の共通制御点)
  const [searchParams, setSearchParams] = useSearchParams()
  const get = (k: string) => searchParams.get(k) ?? ''
  const smart = get('mode') === 'smart'

  const setParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setSearchParams(next, { replace: true })
  }

  // q はタイプ中のローカル状態を持ち、キーワードモードでは300msデバウンスでURLへ反映。
  // スマートモードでは Enter / 検索ボタンで確定したときだけURLへ反映(=検索実行)。
  const [qInput, setQInput] = useState(get('q'))
  useEffect(() => {
    setQInput(searchParams.get('q') ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get('q')])
  useEffect(() => {
    if (smart) return
    const t = setTimeout(() => {
      if (qInput !== (searchParams.get('q') ?? '')) setParams({ q: qInput || null })
    }, 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput, smart])

  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  // フィルタが変わったら先頭ページへ
  const filterKey = searchParams.toString()
  useEffect(() => setPage(0), [filterKey, rowsPerPage])

  // マスタ(選択肢)
  const { data: masters } = useMasters()
  const opts = (cat: 'machine' | 'process' | 'customer' | 'operator' | 'phenomenon') =>
    masters?.[cat] ?? []

  // ---- キーワードモードのデータ取得 ----
  const [items, setItems] = useState<Report[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const listParams = useMemo(
    () => ({
      q: get('q') || undefined,
      status: get('status') || undefined,
      severity: get('severity') || undefined,
      machine: get('machine') || undefined,
      process: get('process') || undefined,
      customer: get('customer') || undefined,
      operator: get('operator') || undefined,
      phenomenon: get('phenomenon') || undefined,
      category_4m: get('category_4m') || undefined,
      date_from: get('date_from') || undefined,
      date_to: get('date_to') || undefined,
      sort: get('sort') || undefined,
      limit: rowsPerPage,
      offset: page * rowsPerPage,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filterKey, rowsPerPage, page],
  )

  useEffect(() => {
    if (smart) return
    let alive = true
    setLoading(true)
    setError(null)
    fetchReports(listParams)
      .then((data) => {
        if (!alive) return
        setItems(data.items)
        setTotal(data.total)
      })
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [listParams, smart])

  // ---- スマートモードのデータ取得(q確定時に実行) ----
  const [smartItems, setSmartItems] = useState<SmartSearchResult[]>([])
  const [smartLoading, setSmartLoading] = useState(false)
  const smartQ = get('q')
  useEffect(() => {
    if (!smart || !smartQ) return
    let alive = true
    setSmartLoading(true)
    setError(null)
    smartSearchReports({
      q: smartQ,
      top_k: 15,
      machine: get('machine') || undefined,
      process: get('process') || undefined,
    })
      .then((d) => alive && setSmartItems(d.items))
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setSmartLoading(false))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smart, smartQ, get('machine'), get('process')])

  const submitSmart = () => setParams({ q: qInput || null })

  const selectField = (
    label: string,
    key: string,
    options: { value: string; label: string }[],
    opt?: { disabled?: boolean; width?: number },
  ) => (
    <Tooltip title={opt?.disabled ? 'スマート検索では機械・工程のみ絞り込めます' : ''} key={key}>
      <TextField
        select
        label={label}
        value={get(key)}
        onChange={(e) => setParams({ [key]: e.target.value || null })}
        size="small"
        disabled={opt?.disabled}
        sx={{ minWidth: opt?.width ?? 140 }}
      >
        <MenuItem value="">すべて</MenuItem>
        {options.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </TextField>
    </Tooltip>
  )

  return (
    <Box>
      <PageHeader
        title="不適合報告書 一覧・検索"
        subtitle="全項目フィルタ+スマート検索(意味検索)。AIアシスタントからも同じ条件で操作できます"
        action={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/reports/new')}>
            新規作成
          </Button>
        }
      />

      <Card sx={{ p: 2, mb: 2 }}>
        {/* 検索モード + キーワード入力 */}
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center', mb: 1.5 }}>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={smart ? 'smart' : 'keyword'}
            onChange={(_, v) => v && setParams({ mode: v === 'smart' ? 'smart' : null })}
          >
            <ToggleButton value="keyword" sx={{ px: 1.5 }}>
              <SearchIcon fontSize="small" sx={{ mr: 0.5 }} />
              キーワード
            </ToggleButton>
            <ToggleButton value="smart" sx={{ px: 1.5 }}>
              <AutoAwesomeIcon fontSize="small" sx={{ mr: 0.5 }} />
              スマート検索
            </ToggleButton>
          </ToggleButtonGroup>
          <TextField
            label={smart ? 'スマート検索(自然文で入力し Enter)' : 'キーワード検索'}
            placeholder={
              smart
                ? '例: 治具の固定が甘くてワークがずれた'
                : '報告書ID・部品名・部品番号・不具合内容'
            }
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => {
              if (smart && e.key === 'Enter') submitSmart()
            }}
            size="small"
            sx={{ flex: '1 1 340px' }}
          />
          {smart && (
            <Button variant="contained" size="small" onClick={submitSmart} disabled={!qInput.trim()}>
              検索
            </Button>
          )}
        </Box>

        {/* フィルタ群(スマート時は機械・工程のみ有効) */}
        <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
          {selectField('ステータス', 'status', STATUSES.map((s) => ({ value: s, label: STATUS_LABELS[s] })), { disabled: smart })}
          {selectField('重要度', 'severity', SEVERITIES.map((s) => ({ value: s, label: SEVERITY_LABELS[s] })), { disabled: smart, width: 120 })}
          {selectField('機械', 'machine', opts('machine').map((m) => ({ value: m.name, label: m.name + (!m.is_active ? '(無効)' : '') })), { width: 170 })}
          {selectField('工程', 'process', opts('process').map((m) => ({ value: m.name, label: m.name })), { width: 120 })}
          {selectField('客先', 'customer', opts('customer').map((m) => ({ value: m.name, label: m.name })), { disabled: smart, width: 150 })}
          {selectField('担当者', 'operator', opts('operator').map((m) => ({ value: m.name, label: m.name })), { disabled: smart, width: 120 })}
          {selectField('現象', 'phenomenon', opts('phenomenon').map((m) => ({ value: m.name, label: m.name })), { disabled: smart, width: 140 })}
          {selectField('4M', 'category_4m', CATEGORY_4M.map((c) => ({ value: c, label: `${c}(${CATEGORY_4M_LABELS[c] ?? c})` })), { disabled: smart, width: 150 })}
          {selectField('並び順', 'sort', SORT_OPTIONS.map(([v, l]) => ({ value: v, label: l })), { disabled: smart, width: 170 })}
        </Box>
      </Card>

      {!smart && <PeriodFilter />}

      {error && <ErrorState message={error} />}

      {/* ---- スマート検索の結果 ---- */}
      {smart ? (
        smartLoading ? (
          <Loading />
        ) : !smartQ ? (
          <EmptyState message="自然文で入力して Enter か「検索」を押すと、意味の近い報告書を探します" />
        ) : smartItems.length === 0 ? (
          <EmptyState message="似た内容の報告書が見つかりませんでした" />
        ) : (
          <Card>
            <TableContainer component={Paper} elevation={0}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>報告書ID</TableCell>
                    <TableCell>部品名</TableCell>
                    <TableCell>機械</TableCell>
                    <TableCell>工程</TableCell>
                    <TableCell>現象</TableCell>
                    <TableCell>内容(抜粋)</TableCell>
                    <TableCell align="right">類似度</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {smartItems.map((r) => (
                    <TableRow
                      key={r.defect_id}
                      hover
                      sx={{ cursor: 'pointer' }}
                      onClick={() => navigate(`/reports/${r.defect_id}`)}
                    >
                      <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{r.defect_id}</TableCell>
                      <TableCell>{r.part_name}</TableCell>
                      <TableCell>{r.machine_name}</TableCell>
                      <TableCell>{r.process}</TableCell>
                      <TableCell>{r.phenomenon}</TableCell>
                      <TableCell sx={{ maxWidth: 340 }}>
                        <Typography variant="caption" color="text.secondary" noWrap component="div">
                          {r.snippet}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip size="small" label={r.score.toFixed(3)} variant="outlined" color="primary" />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Card>
        )
      ) : loading ? (
        <Loading />
      ) : (
        /* ---- キーワードモードの結果 ---- */
        <Card>
          <TableContainer component={Paper} elevation={0}>
            <Table size="small">
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
                {items.map((r) => (
                  <TableRow
                    key={r.defect_id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/reports/${r.defect_id}`)}
                  >
                    <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{r.defect_id}</TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDate(r.occurrence_date)}</TableCell>
                    <TableCell>{r.part_name}</TableCell>
                    <TableCell>{r.phenomenon}</TableCell>
                    <TableCell>{r.machine_name}</TableCell>
                    <TableCell>
                      <SeverityChip severity={r.severity as Severity} />
                    </TableCell>
                    <TableCell>
                      <StatusChip status={r.status as Status} />
                    </TableCell>
                    <TableCell align="right">{formatPercent(r.defect_rate, 2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {items.length === 0 && <EmptyState message="条件に一致する報告書がありません" />}
          <TablePagination
            component="div"
            count={total}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => setRowsPerPage(parseInt(e.target.value, 10))}
            rowsPerPageOptions={[10, 25, 50]}
            labelRowsPerPage="表示件数"
          />
        </Card>
      )}
    </Box>
  )
}
