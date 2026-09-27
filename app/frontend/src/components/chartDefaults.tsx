import type { CSSProperties, ReactNode } from 'react'
import { useTheme } from '@mui/material/styles'
import type { ChartPalette } from '../theme'

// Recharts のダーク/ライト両対応スタイルをテーマから供給する。
// 各チャートページは useChartDefaults() で取得し、tooltip/軸/グリッド/凡例に適用する。
export interface ChartDefaults {
  chart: ChartPalette
  tooltipProps: {
    contentStyle: CSSProperties
    labelStyle: CSSProperties
    itemStyle: CSSProperties
    cursor: { fill: string }
  }
  axisTick: { fontSize: number; fill: string }
  gridStroke: string
  legendText: (value: ReactNode) => ReactNode
}

export function useChartDefaults(): ChartDefaults {
  const theme = useTheme()
  const { app, text, chart } = theme.palette
  const secondary = text.secondary
  const primary = text.primary

  return {
    chart,
    tooltipProps: {
      contentStyle: {
        background: app.elevated,
        border: `1px solid ${app.hairline}`,
        borderRadius: 8,
        color: primary,
        fontSize: 12,
      },
      labelStyle: { color: secondary, marginBottom: 4 },
      itemStyle: { color: primary },
      cursor: { fill: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(15,23,42,0.04)' },
    },
    axisTick: { fontSize: 11, fill: chart.axis },
    gridStroke: chart.grid,
    // 凡例テキストは系列色ではなく文字トークンで表示する(dataviz 指針)
    legendText: (value: ReactNode) => <span style={{ color: secondary, fontSize: 12 }}>{value}</span>,
  }
}
