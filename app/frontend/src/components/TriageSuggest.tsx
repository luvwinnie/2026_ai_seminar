/**
 * 新規作成フォームの「AI で分類を提案」 — 入力中の不具合内容と原因を判断モデル(Jev)に見せ、
 * 現象・要因・4M を提案する。確かな提案(閾値以上)だけをまとめて入れ、迷っている項目は候補から人が選ぶ。
 * 何も保存しない(POST /api/triage/preview)。
 */
import { useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Chip, Stack, Typography } from '@mui/material'
import AltRouteIcon from '@mui/icons-material/AltRoute'
import { previewTriage } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { ReportInput, TriageChoiceDecision, TriagePreview } from '../types'
import { AcceptChip, Candidates, JevFooter, JevNotes } from './triageCommon'
import { FIELD_LABELS, useTriageStatus, valueLabel } from '../utils/triage'

const CHOICES = ['phenomenon', 'factor', 'category_4m'] as const

export default function TriageSuggest({
  value,
  onApply,
}: {
  value: ReportInput
  onApply: (patch: Partial<ReportInput>) => void
}) {
  const status = useTriageStatus()
  const [res, setRes] = useState<TriagePreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!status?.enabled) return null

  const ask = async () => {
    setBusy(true)
    setError(null)
    try {
      setRes(
        await previewTriage({
          defect_description: value.defect_description ?? '',
          cause: value.cause ?? null,
          countermeasure: value.countermeasure ?? null,
          process: value.process ?? null,
          machine_name: value.machine_name ?? null,
          part_name: value.part_name ?? null,
        }),
      )
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const accepted: Partial<ReportInput> = {}
  for (const k of CHOICES) {
    const d = res?.decisions[k] as TriageChoiceDecision | undefined
    if (d?.accepted && d.value) (accepted as Record<string, string>)[k] = d.value
  }
  const d = res?.decisions

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <AltRouteIcon color="primary" fontSize="small" />
          <Typography sx={{ fontWeight: 700 }}>AI で分類を提案</Typography>
          <Typography variant="caption" color="text.secondary">
            (判断モデル Jev・約0.5秒。不具合内容と原因を書いてから押す)
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Button size="small" variant="outlined" disabled={busy || !value.defect_description} onClick={ask}>
            {busy ? '判断中…' : '提案する'}
          </Button>
          {res && Object.keys(accepted).length > 0 && (
            <Button size="small" variant="contained" onClick={() => onApply(accepted)}>
              確かな提案({Object.keys(accepted).length}項目)を入れる
            </Button>
          )}
        </Stack>
        {error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
        {d && (
          <Stack spacing={1} sx={{ mt: 1.5 }}>
            {CHOICES.map((k) => {
              const x = d[k] as TriageChoiceDecision | undefined
              if (!x) return null
              return (
                <Stack key={k} direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', rowGap: 0.5 }}>
                  <Typography variant="body2" sx={{ width: 90, fontWeight: 600 }}>
                    {FIELD_LABELS[k]}
                  </Typography>
                  <AcceptChip accepted={x.accepted} source={x.source} />
                  {x.accepted ? (
                    <Typography variant="body2">{valueLabel(k, x.value)}</Typography>
                  ) : (
                    <>
                      <Candidates field={k} decision={x} onPick={(v) => onApply({ [k]: v } as Partial<ReportInput>)} />
                      <Typography variant="caption" color="text.secondary">
                        (候補を押すとフォームに入ります)
                      </Typography>
                    </>
                  )}
                </Stack>
              )
            })}
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
              {d.severity && (
                <Chip
                  size="small"
                  variant="outlined"
                  label={`重要度の参考: ${valueLabel('severity', d.severity.value)}(人が決める)`}
                />
              )}
              {d.outflow?.value && d.outflow.accepted && <Chip size="small" color="error" label="客先流出の疑い" />}
              {d.systemic?.value && d.systemic.accepted && (
                <Chip size="small" color="warning" label="仕組みの原因(再発のおそれ)" />
              )}
              {d.info_missing?.value && d.info_missing.accepted && (
                <Chip
                  size="small"
                  color="warning"
                  label={d.info_missing.source === 'rule' ? '原因が空欄です' : '記述が足りない可能性'}
                />
              )}
            </Stack>
            <JevNotes jev={res!.jev} />
            <JevFooter jev={res!.jev} />
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
