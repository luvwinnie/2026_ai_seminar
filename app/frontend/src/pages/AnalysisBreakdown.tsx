import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
} from '@mui/material'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import PageHeader from '../components/PageHeader'
import PeriodFilter from '../components/PeriodFilter'
import ChartCard from '../components/ChartCard'
import { Loading, ErrorState, EmptyState } from '../components/StateViews'
import { fetchStatistics } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { BreakdownRow, DashboardStatistics } from '../types'
import { useChartDefaults } from '../components/chartDefaults'
import { formatCurrency, formatNumber, formatPercent } from '../utils/format'

type Kind = 'machine' | 'operator' | 'customer'

const CONFIG: Record<Kind, { title: string; subtitle: string; label: string; key: keyof DashboardStatistics }> = {
  machine: { title: '機械別 分析', subtitle: '機械ごとの不良率・件数・損失額', label: '機械', key: 'by_machine' },
  operator: { title: '担当者別 分析', subtitle: '作業者ごとの不良率・件数・損失額', label: '担当者', key: 'by_operator' },
  customer: { title: '顧客別 分析', subtitle: '客先ごとの不良率・件数・損失額', label: '客先', key: 'by_customer' },
}

type SortKey = keyof Pick<BreakdownRow, 'name' | 'reports' | 'defects' | 'defect_rate' | 'total_cost'>

export default function AnalysisBreakdown({ kind }: { kind: Kind }) {
  const config = CONFIG[kind]
  const [stats, setStats] = useState<DashboardStatistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // URLクエリの期間指定(WebMCP: ui_navigate から制御される)
  const [searchParams] = useSearchParams()
  const dateFrom = searchParams.get('date_from') ?? undefined
  const dateTo = searchParams.get('date_to') ?? undefined

  const [sortBy, setSortBy] = useState<SortKey>('defect_rate')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')

  // URLクエリのソート指定(WebMCP: ui_navigate から制御される)
  useEffect(() => {
    const sp = searchParams.get('sort_by')
    if (sp && ['name', 'reports', 'defects', 'defect_rate', 'total_cost'].includes(sp)) {
      setSortBy(sp as SortKey)
    }
    const op = searchParams.get('order')
    if (op === 'asc' || op === 'desc') setOrder(op)
  }, [searchParams])
  const { chart, tooltipProps, axisTick, gridStroke } = useChartDefaults()

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    fetchStatistics({ date_from: dateFrom, date_to: dateTo })
      .then((data) => alive && setStats(data))
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [dateFrom, dateTo])

  const rows = useMemo(
    () => (stats?.[config.key] as BreakdownRow[] | undefined) ?? [],
    [stats, config.key],
  )

  const sorted = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const av = a[sortBy]
      const bv = b[sortBy]
      let cmp: number
      if (typeof av === 'string' && typeof bv === 'string') cmp = av.localeCompare(bv)
      else cmp = (av as number) - (bv as number)
      return order === 'asc' ? cmp : -cmp
    })
    return copy
  }, [rows, sortBy, order])

  // グラフは不良率の高い順に上位15件
  const chartData = useMemo(
    () => [...rows].sort((a, b) => b.defect_rate - a.defect_rate).slice(0, 15),
    [rows],
  )

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) setOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
    else {
      setSortBy(key)
      setOrder('desc')
    }
  }

  const headCell = (key: SortKey, label: string, align: 'left' | 'right' = 'right') => (
    <TableCell align={align} sortDirection={sortBy === key ? order : false}>
      <TableSortLabel active={sortBy === key} direction={sortBy === key ? order : 'desc'} onClick={() => toggleSort(key)}>
        {label}
      </TableSortLabel>
    </TableCell>
  )

  if (loading) return <Loading />
  if (error) return <ErrorState message={error} />

  return (
    <Box>
      <PageHeader title={config.title} subtitle={config.subtitle} />
      <PeriodFilter />

      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <ChartCard title={`${config.label}別 不良率(上位15件)`} subtitle="不良率が高い順" height={Math.max(280, chartData.length * 28)}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} tick={axisTick} />
                <YAxis type="category" dataKey="name" width={110} tick={axisTick} />
                <Tooltip
                  {...tooltipProps}
                  formatter={(v) => (typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : String(v))}
                />
                <Bar dataKey="defect_rate" name="不良率" radius={[0, 4, 4, 0]}>
                  {chartData.map((_, i) => (
                    // 不良率ワースト上位3件はアンバーで強調、それ以外は steel-cyan
                    <Cell key={i} fill={i < 3 ? chart.amber : chart.cyan} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <Card sx={{ mt: 3 }}>
            <CardContent sx={{ p: 0 }}>
              <TableContainer component={Paper} elevation={0}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {headCell('name', config.label, 'left')}
                      {headCell('reports', '報告件数')}
                      {headCell('defects', '不適合数')}
                      {headCell('defect_rate', '不良率')}
                      {headCell('total_cost', '損失額')}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sorted.map((r) => (
                      <TableRow key={r.name} hover>
                        <TableCell sx={{ fontWeight: 600 }}>{r.name}</TableCell>
                        <TableCell align="right">{formatNumber(r.reports)}</TableCell>
                        <TableCell align="right">{formatNumber(r.defects)}</TableCell>
                        <TableCell align="right">{formatPercent(r.defect_rate, 2)}</TableCell>
                        <TableCell align="right">{formatCurrency(r.total_cost)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </>
      )}
    </Box>
  )
}
