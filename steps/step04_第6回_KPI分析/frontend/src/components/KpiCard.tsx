import { Card, CardContent, Typography } from '@mui/material'
import type { ReactNode } from 'react'

/** KPI 表示カード。値を大きく、補足を下に表示する */
export default function KpiCard({
  label,
  value,
  sub,
  accent = '#2563eb',
  icon,
}: {
  label: string
  value: ReactNode
  sub?: string
  accent?: string
  icon?: ReactNode
}) {
  return (
    <Card sx={{ height: '100%', borderTop: `3px solid ${accent}` }}>
      <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ display: 'flex', alignItems: 'center', gap: 0.5, fontWeight: 600 }}
        >
          {icon}
          {label}
        </Typography>
        <Typography sx={{ fontSize: 30, fontWeight: 800, lineHeight: 1.15, color: '#0f172a' }}>
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
