/**
 * CAPA(是正・予防処置)一覧(docs/10 A-3)。URLクエリ(status/overdue)はAIのui_navigateと共有。
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Card,
  Chip,
  MenuItem,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
} from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import PageHeader from '../components/PageHeader'
import { EmptyState, Loading } from '../components/StateViews'
import { fetchCapaList, updateCapa } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { CapaAction } from '../types'

export const CAPA_STATUS_LABELS: Record<string, string> = {
  open: '未着手',
  in_progress: '対応中',
  effect_check: '効果確認',
  closed: '完了',
}
const STATUS_COLOR: Record<string, 'default' | 'warning' | 'info' | 'success'> = {
  open: 'warning',
  in_progress: 'info',
  effect_check: 'info',
  closed: 'success',
}

export default function Capa() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const status = searchParams.get('status') ?? ''
  const overdue = searchParams.get('overdue') === 'true'

  const [items, setItems] = useState<CapaAction[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const d = await fetchCapaList({
        status: status || undefined,
        overdue: overdue ? true : undefined,
      })
      setItems(d.items)
    } catch (e) {
      setError(errorMessage(e))
    }
  }, [status, overdue])

  useEffect(() => {
    reload()
  }, [reload])

  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (v) next.set(k, v)
    else next.delete(k)
    setSearchParams(next, { replace: true })
  }

  const changeStatus = async (a: CapaAction, next: string) => {
    try {
      let effect_note: string | undefined
      if (next === 'closed') {
        const note = window.prompt('効果確認メモ(closedへの遷移に必須)', a.effect_note ?? '')
        if (note === null) return
        effect_note = note || '効果確認済み'
      }
      await updateCapa(a.capa_id, { status: next, effect_note } as Partial<CapaAction>)
      reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Box>
      <PageHeader
        title="是正・予防処置(CAPA)"
        subtitle="不適合に対する処置のライフサイクル管理(起票 → 対応 → 効果確認 → 完了)"
      />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Card sx={{ p: 2, mb: 2, display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
        <TextField
          select
          label="ステータス"
          value={status}
          onChange={(e) => setParam('status', e.target.value || null)}
          size="small"
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">すべて</MenuItem>
          {Object.entries(CAPA_STATUS_LABELS).map(([v, l]) => (
            <MenuItem key={v} value={v}>{l}</MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="期限"
          value={overdue ? 'overdue' : ''}
          onChange={(e) => setParam('overdue', e.target.value === 'overdue' ? 'true' : null)}
          size="small"
          sx={{ minWidth: 140 }}
        >
          <MenuItem value="">すべて</MenuItem>
          <MenuItem value="overdue">期限超過のみ</MenuItem>
        </TextField>
      </Card>

      {items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState message="該当する処置がありません。報告書詳細の「CAPA」から起票できます" />
      ) : (
        <Card>
          <TableContainer component={Paper} elevation={0}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>CAPA ID</TableCell>
                  <TableCell>報告書</TableCell>
                  <TableCell>種別</TableCell>
                  <TableCell>処置内容</TableCell>
                  <TableCell>担当</TableCell>
                  <TableCell>期限</TableCell>
                  <TableCell>ステータス</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((a) => (
                  <TableRow key={a.capa_id} hover>
                    <TableCell sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{a.capa_id}</TableCell>
                    <TableCell
                      sx={{ whiteSpace: 'nowrap', cursor: 'pointer', color: 'primary.main', fontWeight: 700 }}
                      onClick={() => navigate(`/reports/${a.defect_id}`)}
                    >
                      {a.defect_id}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label={a.action_type === 'preventive' ? '予防' : '是正'} />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 340 }}>
                      <Tooltip title={a.description ?? ''}>
                        <span>{a.title}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>{a.owner ?? '-'}</TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>
                      {a.due_date ?? '-'}
                      {a.overdue && (
                        <Tooltip title="期限超過">
                          <WarningAmberIcon color="error" sx={{ fontSize: 16, ml: 0.5, verticalAlign: 'text-bottom' }} />
                        </Tooltip>
                      )}
                    </TableCell>
                    <TableCell>
                      <TextField
                        select
                        size="small"
                        value={a.status}
                        onChange={(e) => changeStatus(a, e.target.value)}
                        variant="standard"
                        slotProps={{
                          select: {
                            renderValue: (v) => (
                              <Chip size="small" color={STATUS_COLOR[v as string]} label={CAPA_STATUS_LABELS[v as string]} />
                            ),
                          },
                        }}
                      >
                        {Object.entries(CAPA_STATUS_LABELS).map(([v, l]) => (
                          <MenuItem key={v} value={v}>{l}</MenuItem>
                        ))}
                      </TextField>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      )}
    </Box>
  )
}
