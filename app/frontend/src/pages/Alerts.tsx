import { useEffect, useState } from 'react'
import { Alert, AlertTitle, Box, Chip, Stack } from '@mui/material'
import PrecisionManufacturingIcon from '@mui/icons-material/PrecisionManufacturing'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import PageHeader from '../components/PageHeader'
import { Loading, ErrorState, EmptyState } from '../components/StateViews'
import { fetchAlerts } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { AlertItem } from '../types'

// アラートレベル → MUI Alert の severity
const LEVEL_SEVERITY: Record<AlertItem['level'], 'error' | 'warning' | 'info'> = {
  critical: 'error',
  warning: 'warning',
  info: 'info',
}

export default function Alerts() {
  const [items, setItems] = useState<AlertItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchAlerts()
      .then((data) => alive && setItems(data.items))
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  return (
    <Box>
      <PageHeader
        title="予測アラート"
        subtitle="ルールベースの予兆検知(不良率の急増・現象の集中・再発発生)"
      />
      {loading && <Loading />}
      {error && <ErrorState message={error} />}
      {items && items.length === 0 && <EmptyState message="現在アラートはありません" />}
      {items && items.length > 0 && (
        <Stack spacing={2}>
          {items.map((a, i) => (
            <Alert key={i} severity={LEVEL_SEVERITY[a.level]} icon={<WarningAmberIcon />} variant="outlined">
              <AlertTitle sx={{ fontWeight: 700 }}>{a.title}</AlertTitle>
              {a.message}
              {a.related && (a.related.machine || a.related.phenomenon) && (
                <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {a.related.machine && (
                    <Chip
                      size="small"
                      icon={<PrecisionManufacturingIcon />}
                      label={`機械: ${a.related.machine}`}
                      variant="outlined"
                    />
                  )}
                  {a.related.phenomenon && (
                    <Chip size="small" label={`現象: ${a.related.phenomenon}`} variant="outlined" />
                  )}
                </Box>
              )}
            </Alert>
          ))}
        </Stack>
      )}
    </Box>
  )
}
