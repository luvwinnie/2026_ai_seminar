import { useEffect, useState } from 'react'
import { Box } from '@mui/material'
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import PageHeader from '../components/PageHeader'
import ChartCard from '../components/ChartCard'
import { Loading, ErrorState } from '../components/StateViews'
import { fetchControlChart, fetchStatistics } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { ControlChartPoint, ControlChartResponse, DashboardStatistics } from '../types'

// p が UCL を超える点を赤で強調表示するカスタムドット
interface ControlDotProps {
  cx?: number
  cy?: number
  payload?: ControlChartPoint
}

function ControlDot({ cx, cy, payload }: ControlDotProps) {
  if (cx == null || cy == null || !payload) return <g />
  const outOfControl = payload.p > payload.ucl
  return (
    <circle
      cx={cx}
      cy={cy}
      r={outOfControl ? 5 : 3}
      fill={outOfControl ? '#dc2626' : '#2563eb'}
      stroke="#fff"
      strokeWidth={1}
    />
  )
}

export default function AnalysisTrends() {
  const [stats, setStats] = useState<DashboardStatistics | null>(null)
  const [chart, setChart] = useState<ControlChartResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    Promise.all([fetchStatistics(), fetchControlChart(12)])
      .then(([s, c]) => {
        if (!alive) return
        setStats(s)
        setChart(c)
      })
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} />
  if (!stats || !chart) return null

  const pctTick = (v: number) => `${(v * 100).toFixed(1)}%`

  return (
    <Box>
      <PageHeader title="時系列分析" subtitle="月次トレンドと p 管理図(工程の統計的管理状態)" />

      <ChartCard title="月次トレンド" subtitle="報告件数・不適合数・不良率の推移" height={340}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={stats.monthly_trend} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tickFormatter={pctTick} tick={{ fontSize: 11 }} />
            <Tooltip
              formatter={(v, name) =>
                name === '不良率' && typeof v === 'number' ? pctTick(v) : String(v)
              }
            />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="reports" name="報告件数" stroke="#2563eb" strokeWidth={2} />
            <Line yAxisId="left" type="monotone" dataKey="defects" name="不適合数" stroke="#f59e0b" strokeWidth={2} />
            <Line yAxisId="right" type="monotone" dataKey="defect_rate" name="不良率" stroke="#dc2626" strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      <Box sx={{ mt: 3 }}>
        <ChartCard
          title="p 管理図"
          subtitle={`不良率 p と管理限界(UCL/LCL)。中心線 p̄ = ${(chart.p_bar * 100).toFixed(2)}%。UCL 超過点は赤で表示`}
          height={360}
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chart.items} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={pctTick} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => (typeof v === 'number' ? pctTick(v) : String(v))} />
              <Legend />
              <ReferenceLine y={chart.p_bar} stroke="#16a34a" strokeDasharray="6 4" label={{ value: 'p̄', position: 'right', fill: '#16a34a' }} />
              <Line type="monotone" dataKey="ucl" name="UCL" stroke="#dc2626" strokeDasharray="5 5" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="lcl" name="LCL" stroke="#0ea5e9" strokeDasharray="5 5" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="p" name="不良率 p" stroke="#2563eb" strokeWidth={2} dot={<ControlDot />} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>
    </Box>
  )
}
