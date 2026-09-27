import { Box, Card, CardContent, Typography } from '@mui/material'
import type { ReactNode } from 'react'

/** グラフや表を囲む共通カード。タイトル + 任意の補足 */
export default function ChartCard({
  title,
  subtitle,
  height,
  children,
}: {
  title: string
  subtitle?: string
  height?: number
  children: ReactNode
}) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontSize: 16 }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {subtitle}
          </Typography>
        )}
        <Box sx={{ mt: 1, height }}>{children}</Box>
      </CardContent>
    </Card>
  )
}
