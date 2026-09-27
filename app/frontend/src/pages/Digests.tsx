/**
 * 週次品質ダイジェスト(docs/10 A-2) — AIが生成するMarkdownレポートの一覧・閲覧。
 * 「今すぐ生成」で手動生成。定期実行は cron から POST /api/digests/generate を叩く運用。
 */
import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
} from '@mui/material'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import PageHeader from '../components/PageHeader'
import MarkdownMessage from '../components/MarkdownMessage'
import { EmptyState, Loading } from '../components/StateViews'
import { fetchDigests, generateDigest } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { WeeklyDigest } from '../types'

export default function Digests() {
  const [items, setItems] = useState<WeeklyDigest[] | null>(null)
  const [selected, setSelected] = useState<WeeklyDigest | null>(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async (selectFirst = false) => {
    try {
      const d = await fetchDigests()
      setItems(d.items)
      if (selectFirst || !selected) setSelected(d.items[0] ?? null)
    } catch (e) {
      setError(errorMessage(e))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    reload(true)
  }, [reload])

  const generate = async () => {
    setGenerating(true)
    setError(null)
    try {
      const d = await generateDigest(7)
      setSelected(d)
      await reload()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Box>
      <PageHeader
        title="週次品質レポート"
        subtitle="KPI前週比・重大案件・アラートをAIが要約(チャットで「週次レポートを出して」でも生成可)"
        action={
          <Button
            variant="contained"
            startIcon={generating ? <CircularProgress size={16} color="inherit" /> : <AutoAwesomeIcon />}
            onClick={generate}
            disabled={generating}
          >
            {generating ? '生成中…' : '今すぐ生成'}
          </Button>
        }
      />
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {items === null ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState message="まだレポートがありません。「今すぐ生成」を押してください" />
      ) : (
        <Box sx={{ display: 'flex', gap: 2, flexDirection: { xs: 'column', md: 'row' } }}>
          <Paper variant="outlined" sx={{ width: { md: 260 }, flexShrink: 0, borderRadius: 2, maxHeight: 560, overflowY: 'auto' }}>
            <List dense>
              {items.map((d) => (
                <ListItemButton key={d.id} selected={selected?.id === d.id} onClick={() => setSelected(d)}>
                  <ListItemText
                    primary={`${d.period_start} 〜 ${d.period_end}`}
                    secondary={d.ai_backend === 'opencode' ? 'AI所見つき' : '集計のみ'}
                  />
                </ListItemButton>
              ))}
            </List>
          </Paper>
          <Card sx={{ flex: 1, minWidth: 0 }}>
            <CardContent>
              {selected ? (
                <>
                  <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                    <Chip size="small" label={`生成: ${selected.created_at?.slice(0, 16).replace('T', ' ')}`} />
                    {selected.ai_backend === 'opencode' && (
                      <Chip size="small" color="primary" variant="outlined" icon={<AutoAwesomeIcon />} label="AI所見つき" />
                    )}
                  </Stack>
                  <MarkdownMessage text={selected.content_md} />
                </>
              ) : (
                <EmptyState message="左の一覧から選択してください" />
              )}
            </CardContent>
          </Card>
        </Box>
      )}
    </Box>
  )
}
