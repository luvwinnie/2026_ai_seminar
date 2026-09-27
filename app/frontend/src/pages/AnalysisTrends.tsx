import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
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
import PeriodFilter from '../components/PeriodFilter'
import ChartCard from '../components/ChartCard'
import { Loading, ErrorState } from '../components/StateViews'
import { fetchControlChart, fetchStatistics } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { ControlChartPoint, ControlChartResponse, DashboardStatistics } from '../types'
import { useTheme } from '@mui/material/styles'
import { useChartDefaults } from '../components/chartDefaults'

// p が UCL を超える点を赤で強調表示するカスタムドット(色はテーマから props で受ける)
interface ControlDotProps {
  cx?: number
  cy?: number
  payload?: ControlChartPoint
  okColor?: string
  dangerColor?: string
  ring?: string
}

function ControlDot({ cx, cy, payload, okColor, dangerColor, ring }: ControlDotProps) {
  if (cx == null || cy == null || !payload) return <g />
  const outOfControl = payload.p > payload.ucl
  return (
    <circle
      cx={cx}
      cy={cy}
      r={outOfControl ? 5 : 3}
      fill={outOfControl ? dangerColor : okColor}
      stroke={ring}
      strokeWidth={1.5}
    />
  )
}

export default function AnalysisTrends() {
  const [stats, setStats] = useState<DashboardStatistics | null>(null)
  const [controlChart, setControlChart] = useState<ControlChartResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { palette } = useTheme()
  const { chart, tooltipProps, axisTick, gridStroke, legendText } = useChartDefaults()

  // URLクエリの期間・月数指定(WebMCP: ui_navigate から制御される)
  const [searchParams] = useSearchParams()
  const dateFrom = searchParams.get('date_from') ?? undefined
  const dateTo = searchParams.get('date_to') ?? undefined
  const months = Number(searchParams.get('months') ?? 12) || 12

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    Promise.all([
      fetchStatistics({ date_from: dateFrom, date_to: dateTo }),
      fetchControlChart(months),
    ])
      .then(([s, c]) => {
        if (!alive) return
        setStats(s)
        setControlChart(c)
      })
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [dateFrom, dateTo, months])

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} />
  if (!stats || !controlChart) return null

  const pctTick = (v: number) => `${(v * 100).toFixed(1)}%`

  return (
    <Box>
      <PageHeader title="時系列分析" subtitle="月次トレンドと p 管理図(工程の統計的管理状態)" />
      <PeriodFilter withMonths />

      <ChartCard title="月次トレンド" subtitle="報告件数・不適合数・不良率の推移" height={340}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={stats.monthly_trend} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis dataKey="month" tick={axisTick} />
            <YAxis yAxisId="left" tick={axisTick} />
            <YAxis yAxisId="right" orientation="right" tickFormatter={pctTick} tick={axisTick} />
            <Tooltip
              {...tooltipProps}
              formatter={(v, name) =>
                name === '不良率' && typeof v === 'number' ? pctTick(v) : String(v)
              }
            />
            <Legend formatter={legendText} />
            <Line yAxisId="left" type="monotone" dataKey="reports" name="報告件数" stroke={palette.text.secondary} strokeWidth={2} dot={{ r: 2 }} />
            <Line yAxisId="left" type="monotone" dataKey="defects" name="不適合数" stroke={chart.cyan} strokeWidth={2} dot={{ r: 2 }} />
            <Line yAxisId="right" type="monotone" dataKey="defect_rate" name="不良率" stroke={chart.amber} strokeWidth={2.5} dot={{ r: 2 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      <Box sx={{ mt: 3 }}>
        <ChartCard
          title="p 管理図"
          subtitle={`不良率 p と管理限界(UCL/LCL)。中心線 p̄ = ${(controlChart.p_bar * 100).toFixed(2)}%。UCL 超過点は赤で表示`}
          height={360}
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={controlChart.items} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
              <XAxis dataKey="period" tick={axisTick} />
              <YAxis tickFormatter={pctTick} tick={axisTick} />
              <Tooltip {...tooltipProps} formatter={(v) => (typeof v === 'number' ? pctTick(v) : String(v))} />
              <Legend formatter={legendText} />
              <ReferenceLine
                y={controlChart.p_bar}
                stroke={chart.neutral}
                strokeDasharray="6 4"
                label={{ value: 'p̄', position: 'right', fill: chart.neutral }}
              />
              <Line type="monotone" dataKey="ucl" name="UCL" stroke={chart.danger} strokeDasharray="5 5" dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="lcl" name="LCL" stroke={chart.danger} strokeDasharray="5 5" dot={false} strokeWidth={1.5} />
              <Line
                type="monotone"
                dataKey="p"
                name="不良率 p"
                stroke={chart.cyan}
                strokeWidth={2}
                dot={<ControlDot okColor={chart.cyan} dangerColor={chart.danger} ring={palette.app.paper} />}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>
    </Box>
  )
}
