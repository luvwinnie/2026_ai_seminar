import { Card, CardContent, Typography } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import type { ReactNode } from 'react'
import { MONO_FONT } from '../theme'

/** KPI 表示カード。値は等幅フォントで計器の読み出し風に、左端にアクセントバー。 */
export default function KpiCard({
  label,
  value,
  sub,
  accent,
  icon,
}: {
  label: string
  value: ReactNode
  sub?: string
  accent?: string
  icon?: ReactNode
}) {
  const { palette } = useTheme()
  const bar = accent ?? palette.primary.main
  return (
    <Card
      sx={{
        height: '100%',
        // トップの色バーは廃止し、左端 2px のアクセントバーに置換
        borderLeft: `2px solid ${bar}`,
      }}
    >
      <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ display: 'flex', alignItems: 'center', gap: 0.5, fontWeight: 600 }}
        >
          {icon}
          {label}
        </Typography>
        <Typography
          sx={{
            fontFamily: MONO_FONT,
            fontSize: 30,
            fontWeight: 700,
            letterSpacing: '-0.01em',
            lineHeight: 1.15,
            color: 'text.primary',
          }}
        >
          {value}
        </Typography>
        {sub && (
          <Typography variant="caption" color="text.secondary">
            {sub}
          </Typography>
        )}
      </CardContent>
    </Card>
  )
}
