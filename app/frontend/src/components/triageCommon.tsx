/**
 * 報告書トリアージ(判断モデル Jev)の表示の共通部品。
 * 判断は「採用(閾値以上)」と「要確認(閾値未満・LLM の提案・参考)」に分けて見せる。
 */
import { Alert, Chip, Stack, Tooltip, Typography } from '@mui/material'
import type { TriageChoiceDecision, TriageJevMeta } from '../types'
import { valueLabel } from '../utils/triage'

export function AcceptChip({ accepted, source }: { accepted: boolean; source?: string }) {
  if (accepted) return <Chip size="small" color="success" variant="outlined" label="採用" />
  return (
    <Chip
      size="small"
      color="warning"
      variant="outlined"
      label={source === 'llm' ? 'LLM の提案・要確認' : '要確認'}
    />
  )
}

/** 候補(確率の高い順)。onPick があればクリックでその値を選べる。 */
export function Candidates({
  field,
  decision,
  onPick,
}: {
  field: string
  decision: TriageChoiceDecision
  onPick?: (value: string) => void
}) {
  if (!decision.top?.length) return null
  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
      {decision.top.map((c) => (
        <Chip
          key={c.value}
          size="small"
          variant={c.value === decision.value ? 'filled' : 'outlined'}
          label={`${valueLabel(field, c.value)} ${(c.p * 100).toFixed(0)}%`}
          onClick={onPick ? () => onPick(c.value) : undefined}
        />
      ))}
    </Stack>
  )
}

/** 確からしさ:1位の確率と、2位との差。採否はこの2つで決める(confidence は2位の近さを見ないため)。 */
export function ProbLabel({ p, margin, confidence }: { p?: number; margin?: number; confidence: number }) {
  const top = p ?? confidence
  return (
    <Tooltip title={`1位の確率 ${(top * 100).toFixed(0)}%・2位との差 ${margin !== undefined ? (margin * 100).toFixed(0) : '—'}・confidence ${(confidence * 100).toFixed(0)}%`}>
      <span>
        {(top * 100).toFixed(0)}%
        {margin !== undefined && (
          <Typography component="span" variant="caption" color="text.secondary">
            {' '}(差 {(margin * 100).toFixed(0)})
          </Typography>
        )}
      </span>
    </Tooltip>
  )
}

/** 自動で採らなかった理由(版が閾値を測ったときと違う、記述が足りない など)。 */
export function JevNotes({ jev }: { jev: TriageJevMeta }) {
  if (!jev.notes?.length) return null
  return (
    <Alert severity="info" sx={{ mt: 1 }}>
      {jev.notes.join('。')}
    </Alert>
  )
}

export function JevFooter({ jev, extra }: { jev: TriageJevMeta; extra?: string }) {
  const yen = jev.cost_usd * 150
  return (
    <Tooltip title={`request id: ${jev.request_ids.filter(Boolean).join(', ')}・質問の指紋 ${jev.criteria_hash ?? '—'}`}>
      <Typography variant="caption" color="text.secondary">
        判断モデル {jev.model}・{jev.calls}回を並列・
        {jev.cached ? '前の答えを使い回し(0円)' : `${(jev.latency_ms / 1000).toFixed(2)}秒・入力 ${jev.input_tokens} トークン・約${yen < 0.01 ? yen.toFixed(4) : yen.toFixed(2)}円`}
        {extra ? `・${extra}` : ''}
      </Typography>
    </Tooltip>
  )
}
