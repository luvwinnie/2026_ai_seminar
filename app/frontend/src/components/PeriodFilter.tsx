/**
 * PeriodFilter — 期間フィルタ(人間とAIの共通制御点=URLクエリ)。
 *
 * 値の正本は URL の date_from / date_to (+ withMonths 時は months)。
 * 人間はこのUIから、AIは ui_navigate から同じパラメータを書き、画面側の
 * fetch は URL を監視しているため、どちらの操作でも同じように反映される。
 */
import { MenuItem, Paper, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import CalendarMonthIcon from '@mui/icons-material/CalendarMonthOutlined'
import { useSearchParams } from 'react-router-dom'

const PRESETS = [
  { key: 'all', label: '全期間', months: null },
  { key: '3m', label: '直近3ヶ月', months: 3 },
  { key: '6m', label: '直近6ヶ月', months: 6 },
  { key: '12m', label: '直近12ヶ月', months: 12 },
] as const

function isoDaysAgoMonths(months: number): string {
  const d = new Date()
  d.setMonth(d.getMonth() - months)
  return d.toISOString().slice(0, 10)
}

export default function PeriodFilter({ withMonths = false }: { withMonths?: boolean }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const dateFrom = searchParams.get('date_from') ?? ''
  const dateTo = searchParams.get('date_to') ?? ''
  const months = searchParams.get('months') ?? '12'

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setSearchParams(next, { replace: true })
  }

  // アクティブなプリセットの判定(from がプリセット計算値と一致し to が空のとき)
  const preset =
    !dateFrom && !dateTo
      ? 'all'
      : (PRESETS.find((p) => p.months && dateFrom === isoDaysAgoMonths(p.months) && !dateTo)?.key ??
        null)

  return (
    <Paper
      variant="outlined"
      sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap', px: 1.5, py: 1, mb: 2, borderRadius: 2 }}
    >
      <CalendarMonthIcon fontSize="small" sx={{ color: 'text.secondary' }} />
      <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
        期間
      </Typography>
      <ToggleButtonGroup
        size="small"
        exclusive
        value={preset}
        onChange={(_, v) => {
          if (!v) return
          const p = PRESETS.find((x) => x.key === v)
          if (!p) return
          set({ date_from: p.months ? isoDaysAgoMonths(p.months) : null, date_to: null })
        }}
      >
        {PRESETS.map((p) => (
          <ToggleButton key={p.key} value={p.key} sx={{ px: 1.25, fontSize: 12 }}>
            {p.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <TextField
        type="date"
        label="開始日"
        size="small"
        value={dateFrom}
        onChange={(e) => set({ date_from: e.target.value || null })}
        slotProps={{ inputLabel: { shrink: true } }}
        sx={{ width: 160 }}
      />
      <TextField
        type="date"
        label="終了日"
        size="small"
        value={dateTo}
        onChange={(e) => set({ date_to: e.target.value || null })}
        slotProps={{ inputLabel: { shrink: true } }}
        sx={{ width: 160 }}
      />
      {withMonths && (
        <TextField
          select
          label="管理図の月数"
          size="small"
          value={months}
          onChange={(e) => set({ months: e.target.value === '12' ? null : e.target.value })}
          sx={{ width: 140 }}
        >
          {['6', '12', '24'].map((m) => (
            <MenuItem key={m} value={m}>
              {m}ヶ月
            </MenuItem>
          ))}
        </TextField>
      )}
    </Paper>
  )
}
