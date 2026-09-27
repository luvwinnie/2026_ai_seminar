import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import PageHeader from '../components/PageHeader'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'
import { Loading, ErrorState } from '../components/StateViews'
import { fetchStatistics } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { DashboardStatistics } from '../types'
import { CHART_COLORS, SEVERITY_CHART_COLORS } from '../theme'
import { formatCurrency, formatNumber, formatPercent } from '../utils/format'
import { SEVERITY_LABELS } from '../constants/vocab'

// レスポンシブなグリッド(カード幅を指定して自動折返し)
function Grid({ children, min = 240 }: { children: ReactNode; min?: number }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))`,
        gap: 2,
      }}
    >
      {children}
    </Box>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStatistics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchStatistics()
      .then((data) => alive && setStats(data))
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} />
  if (!stats) return null

  const { kpi } = stats

  // severity ドーナツ用に日本語ラベルを付与
  const severityData = stats.by_severity.map((s) => ({
    ...s,
    label: SEVERITY_LABELS[s.name as keyof typeof SEVERITY_LABELS] ?? s.name,
  }))

  return (
    <Box>
      <PageHeader title="サマリー" subtitle="不適合報告書の全体傾向とKPI(経営者向けダッシュボード)" />

      <Grid min={220}>
        <KpiCard label="総報告件数" value={formatNumber(kpi.total_reports)} sub="件" accent="#2563eb" />
        <KpiCard label="総不適合数" value={formatNumber(kpi.total_defects)} sub="個" accent="#dc2626" />
        <KpiCard label="不良率" value={formatPercent(kpi.defect_rate, 2)} sub="不適合数 / 加工数" accent="#f59e0b" />
        <KpiCard label="直行率 (FPY)" value={formatPercent(kpi.fpy, 2)} sub="First Pass Yield" accent="#16a34a" />
        <KpiCard label="総損失額" value={formatCurrency(kpi.total_cost)} sub="材料費+加工費+外注+その他" accent="#8b5cf6" />
        <KpiCard label="再発率" value={formatPercent(kpi.recurrence_rate, 1)} sub="再発フラグ付き比率" accent="#ec4899" />
        <KpiCard label="対応中件数" value={formatNumber(kpi.open_count)} sub="未完了(open/in_progress)" accent="#0ea5e9" />
      </Grid>

      <Box sx={{ mt: 3, display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.4fr 1fr' }, gap: 2 }}>
        <ChartCard title="現象別 パレート図" subtitle="件数(棒)と累積比率(折れ線)" height={340}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={stats.pareto_phenomenon} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-30} textAnchor="end" height={70} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis
                yAxisId="right"
                orientation="right"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
                tick={{ fontSize: 11 }}
              />
              <Tooltip
                formatter={(value, name) =>
                  name === '累積比率' && typeof value === 'number'
                    ? `${value.toFixed(1)}%`
                    : String(value)
                }
              />
              <Legend />
              <Bar yAxisId="left" dataKey="count" name="件数" fill="#2563eb" radius={[4, 4, 0, 0]} />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey={(d) => d.cumulative_ratio * 100}
                name="累積比率"
                stroke="#f59e0b"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="重要度の内訳" subtitle="severity 別の件数" height={340}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={severityData}
                dataKey="count"
                nameKey="label"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
              >
                {severityData.map((entry) => (
                  <Cell key={entry.name} fill={SEVERITY_CHART_COLORS[entry.name] ?? '#64748b'} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>

      <Box sx={{ mt: 3, display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1.4fr 1fr' }, gap: 2 }}>
        <ChartCard title="月次トレンド" subtitle="報告件数・不適合数の推移" height={320}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stats.monthly_trend} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="reports" name="報告件数" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} />
              <Line type="monotone" dataKey="defects" name="不適合数" stroke="#dc2626" strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="4M 分類" subtitle="要因カテゴリの内訳" height={320}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={stats.by_4m}
                dataKey="count"
                nameKey="name"
                outerRadius={100}
                label={(entry) => entry.name}
              >
                {stats.by_4m.map((entry, i) => (
                  <Cell key={entry.name} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>
    </Box>
  )
}
