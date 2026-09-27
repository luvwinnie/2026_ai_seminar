import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Button,
  Card,
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
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import SearchIcon from '@mui/icons-material/Search'
import PageHeader from '../components/PageHeader'
import { SeverityChip, StatusChip } from '../components/Chips'
import { Loading, ErrorState, EmptyState } from '../components/StateViews'
import { fetchReports } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { Report, Severity, Status } from '../types'
import { MACHINES, SEVERITIES, SEVERITY_LABELS, STATUSES, STATUS_LABELS } from '../constants/vocab'
import { formatDate, formatPercent } from '../utils/format'

export default function Reports() {
  const navigate = useNavigate()

  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [status, setStatus] = useState('')
  const [severity, setSeverity] = useState('')
  const [machine, setMachine] = useState('')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)

  const [items, setItems] = useState<Report[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // q の入力をデバウンス(300ms)
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(t)
  }, [q])

  // フィルタ変更時は先頭ページへ戻す
  useEffect(() => {
    setPage(0)
  }, [debouncedQ, status, severity, machine, rowsPerPage])

  const params = useMemo(
    () => ({
      q: debouncedQ || undefined,
      status: status || undefined,
      severity: severity || undefined,
      machine: machine || undefined,
      limit: rowsPerPage,
      offset: page * rowsPerPage,
    }),
    [debouncedQ, status, severity, machine, rowsPerPage, page],
  )

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    fetchReports(params)
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
  }, [params])

  return (
    <Box>
      <PageHeader
        title="不適合報告書 一覧・検索"
        subtitle="キーワード・ステータス・重要度・機械で絞り込み"
        action={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/reports/new')}>
            新規作成
          </Button>
        }
      />

      <Card sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <TextField
            label="キーワード検索"
            placeholder="報告書ID・部品名・部品番号・不具合内容"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            size="small"
            sx={{ flex: '1 1 320px' }}
            slotProps={{
              input: {
                startAdornment: <SearchIcon fontSize="small" sx={{ mr: 1, color: 'text.disabled' }} />,
              },
            }}
          />
          <TextField
            select
            label="ステータス"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            size="small"
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">すべて</MenuItem>
            {STATUSES.map((s) => (
              <MenuItem key={s} value={s}>
                {STATUS_LABELS[s]}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="重要度"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            size="small"
            sx={{ minWidth: 130 }}
          >
            <MenuItem value="">すべて</MenuItem>
            {SEVERITIES.map((s) => (
              <MenuItem key={s} value={s}>
                {SEVERITY_LABELS[s]}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="機械"
            value={machine}
            onChange={(e) => setMachine(e.target.value)}
            size="small"
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">すべて</MenuItem>
            {MACHINES.map((m) => (
              <MenuItem key={m} value={m}>
                {m}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      </Card>

      {error && <ErrorState message={error} />}

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

        {loading && <Loading />}
        {!loading && items.length === 0 && <EmptyState message="条件に一致する報告書がありません" />}

        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => setRowsPerPage(parseInt(e.target.value, 10))}
          rowsPerPageOptions={[10, 25, 50, 100]}
          labelRowsPerPage="表示件数"
          labelDisplayedRows={({ from, to, count }) => `${from}–${to} / 全 ${count} 件`}
        />
      </Card>
    </Box>
  )
}
