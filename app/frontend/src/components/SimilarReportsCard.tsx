/**
 * 類似事例サジェスト(docs/10 A-1) — 報告書詳細に「似た過去事例と当時の対策」を自動表示。
 */
import { useEffect, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Box, Card, CardContent, Chip, Divider, Link, Stack, Typography } from '@mui/material'
import TravelExploreIcon from '@mui/icons-material/TravelExplore'
import { fetchSimilarReports } from '../api/endpoints'
import type { SimilarReport } from '../types'

export default function SimilarReportsCard({ defectId }: { defectId: string }) {
  const [items, setItems] = useState<SimilarReport[] | null>(null)

  useEffect(() => {
    let alive = true
    setItems(null)
    fetchSimilarReports(defectId, 3)
      .then((d) => alive && setItems(d.items))
      .catch(() => alive && setItems([]))
    return () => {
      alive = false
    }
  }, [defectId])

  if (items !== null && items.length === 0) return null
  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
          <TravelExploreIcon color="primary" fontSize="small" />
          <Typography sx={{ fontWeight: 700 }}>類似事例と当時の対策</Typography>
          <Typography variant="caption" color="text.secondary">
            (ハイブリッド検索による自動サジェスト)
          </Typography>
        </Stack>
        {items === null ? (
          <Typography variant="body2" color="text.secondary">検索中…</Typography>
        ) : (
          <Stack divider={<Divider />} spacing={1.5}>
            {items.map((s) => (
              <Box key={s.defect_id}>
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <Link component={RouterLink} to={`/reports/${s.defect_id}`} sx={{ fontWeight: 700 }}>
                    {s.defect_id}
                  </Link>
                  <Typography variant="body2" color="text.secondary">
                    {s.occurrence_date} · {s.machine_name} · {s.phenomenon}
                  </Typography>
                  <Chip size="small" variant="outlined" label={`類似度 ${s.score.toFixed(3)}`} />
                </Stack>
                <Typography variant="body2" sx={{ mt: 0.5 }}>
                  <b>当時の対策:</b> {s.countermeasure || '(記載なし)'}
                </Typography>
              </Box>
            ))}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
