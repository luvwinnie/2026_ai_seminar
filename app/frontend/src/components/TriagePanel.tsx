/**
 * 報告書詳細の「AI トリアージ」 — 判断モデル(Jev)が分類と CAPA の要否を判断し、
 * LangGraph の流れで、自信の低い項目だけ LLM へ、CAPA は人の承認で止めてから登録する。
 */
import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Divider,
  FormControlLabel,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material'
import AltRouteIcon from '@mui/icons-material/AltRoute'
import { fetchTriage, resumeTriage, runTriage, updateReport } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { Report, TriageChoiceDecision, TriageRun } from '../types'
import { AcceptChip, Candidates, JevFooter, ProbLabel, JevNotes } from './triageCommon'
import { FIELD_LABELS, SOURCE_LABELS, useTriageStatus, valueLabel } from '../utils/triage'

const NODE_LABELS: Record<string, string> = {
  prepare: '項目を取り出す',
  judge: 'Jev が判断',
  llm_review: 'LLM が確認',
  merge: '登録値と照合',
  plan: 'CAPA の要否',
  draft_capa: '処置案の下書き',
  human_review: '人の承認',
  apply: 'CAPA 登録',
}

const STATUS_TEXT: Record<string, { label: string; color: 'default' | 'success' | 'warning' | 'info' }> = {
  completed: { label: '判定済み', color: 'success' },
  waiting_approval: { label: '承認待ち', color: 'warning' },
  approved: { label: '承認・登録済み', color: 'success' },
  rejected: { label: '却下', color: 'default' },
}

interface Props {
  report: Report
  onReportChanged: () => void
  onCapaCreated: () => void
}

// 処置案を Jev が確かめる3つの問い(原因に対応・再発を防ぐ・具体的)
const CAPA_CHECK_LABELS = { cause: '原因に対応', recurrence: '再発を防ぐ', concrete: '具体的' } as const

export default function TriagePanel({ report, onReportChanged, onCapaCreated }: Props) {
  const status = useTriageStatus()
  const [run, setRun] = useState<TriageRun | null | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<number[]>([])

  useEffect(() => {
    if (!status?.enabled) return
    let alive = true
    fetchTriage(report.defect_id)
      .then((r) => alive && setRun(r))
      .catch(() => alive && setRun(null))
    return () => {
      alive = false
    }
  }, [status?.enabled, report.defect_id])

  useEffect(() => {
    // 承認待ちになったら、Jev の3つの確かめ(原因に対応・再発を防ぐ・具体的)をすべて通った案だけを既定で選んでおく
    const acts = run?.capa_draft?.actions ?? []
    setSelected(acts.map((a, i) => ((a.jev_ok ?? (a.jev_fits_cause ?? 0) >= 0.7) ? i : -1)).filter((i) => i >= 0))
  }, [run?.run_id, run?.status, run?.capa_draft?.actions])

  if (!status?.enabled) return null

  const act = async (fn: () => Promise<TriageRun>, after?: (r: TriageRun) => void) => {
    setBusy(true)
    setError(null)
    try {
      const r = await fn()
      setRun(r)
      after?.(r)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const fixLabel = async (field: string, value: string) => {
    setBusy(true)
    try {
      await updateReport(report.defect_id, { [field]: value })
      onReportChanged()
      setRun((r) => (r ? { ...r, conflicts: (r.conflicts ?? []).filter((c) => c.field !== field) } : r))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const d = run?.decisions
  const registered: Record<string, string | null | undefined> = {
    phenomenon: report.phenomenon,
    factor: report.factor,
    category_4m: report.category_4m,
    severity: report.severity,
  }

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1, flexWrap: 'wrap' }}>
          <AltRouteIcon color="primary" fontSize="small" />
          <Typography sx={{ fontWeight: 700 }}>AI トリアージ</Typography>
          <Typography variant="caption" color="text.secondary">
            (判断モデル Jev が分類と CAPA の要否を判断。自信の低い項目だけ LLM と人へ回す)
          </Typography>
          <Box sx={{ flex: 1 }} />
          {run && <Chip size="small" color={STATUS_TEXT[run.status]?.color} label={STATUS_TEXT[run.status]?.label} />}
          <Button
            size="small"
            variant={run ? 'outlined' : 'contained'}
            disabled={busy || run?.status === 'waiting_approval'}
            onClick={() => act(() => runTriage(report.defect_id))}
          >
            {busy ? '判定中…' : run ? 'もう一度判定' : '判定する'}
          </Button>
        </Stack>

        {error && (
          <Alert severity="error" sx={{ mb: 1 }}>
            {error}
          </Alert>
        )}
        {run === undefined && <Typography variant="body2" color="text.secondary">読み込み中…</Typography>}
        {run === null && (
          <Typography variant="body2" color="text.secondary">
            まだ判定していません。「判定する」で、現象・要因・4M・重要度と、客先流出・再発のおそれを約0.5秒で判断します。
          </Typography>
        )}

        {run && d && (
          <>
            <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5, mb: 1.5 }}>
              {run.route.map((n, i) => (
                <Chip key={`${n}-${i}`} size="small" variant="outlined" label={`${i + 1}. ${NODE_LABELS[n] ?? n}`} />
              ))}
              {run.status === 'waiting_approval' && (
                <Chip size="small" color="warning" label={`${run.route.length + 1}. 人の承認(待ち)`} />
              )}
            </Stack>

            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>項目</TableCell>
                  <TableCell>判断</TableCell>
                  <TableCell>確からしさ</TableCell>
                  <TableCell>登録値</TableCell>
                  <TableCell>扱い</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(['phenomenon', 'factor', 'category_4m'] as const).map((k) => {
                  const x = d[k] as TriageChoiceDecision | undefined
                  if (!x) return null
                  return (
                    <TableRow key={k}>
                      <TableCell>{FIELD_LABELS[k]}</TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {valueLabel(k, x.value)}
                        </Typography>
                        {!x.accepted && <Candidates field={k} decision={x} />}
                        {x.reason && (
                          <Typography variant="caption" color="text.secondary">
                            LLM: {x.reason}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        {k === 'category_4m' && x.source === 'rule'
                          ? `要因から決定${x.rule_agrees_with_jev === false ? `(Jev は ${valueLabel(k, x.jev_value)})` : ''}`
                          : <ProbLabel p={x.p_top} margin={x.margin} confidence={x.confidence} />}
                      </TableCell>
                      <TableCell>{valueLabel(k, registered[k])}</TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5}>
                          <AcceptChip accepted={x.accepted} source={x.source} />
                          <Chip size="small" variant="outlined" label={SOURCE_LABELS[x.source] ?? x.source} />
                        </Stack>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {d.severity && (
                  <TableRow>
                    <TableCell>{FIELD_LABELS.severity}</TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {valueLabel('severity', d.severity.value)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <ProbLabel p={d.severity.p_top} margin={d.severity.margin} confidence={d.severity.confidence} />
                    </TableCell>
                    <TableCell>{valueLabel('severity', registered.severity)}</TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label="参考(人が決める)" />
                    </TableCell>
                  </TableRow>
                )}
                {(['outflow', 'systemic', 'info_missing'] as const).map((k) => {
                  const x = d[k]
                  if (!x) return null
                  return (
                    <TableRow key={k}>
                      <TableCell>{FIELD_LABELS[k]}</TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {x.value ? 'はい' : 'いいえ'}
                        </Typography>
                      </TableCell>
                      <TableCell>{x.source === 'rule' ? '原因が空欄' : `はい ${(x.probability * 100).toFixed(0)}%`}</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>
                        <AcceptChip accepted={x.accepted} source={x.source} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>

            {(run.conflicts ?? []).length > 0 && (
              <Alert severity="warning" sx={{ mt: 1.5 }}>
                <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
                  登録値と、確かな判断が違います(分類の見直し候補)
                </Typography>
                {run.conflicts!.map((c) => (
                  <Stack key={c.field} direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                    <Typography variant="body2">
                      {FIELD_LABELS[c.field]}: 登録「{valueLabel(c.field, c.registered)}」→ 判断「
                      {valueLabel(c.field, c.suggested)}」({(c.confidence * 100).toFixed(0)}%)
                    </Typography>
                    <Button size="small" disabled={busy} onClick={() => fixLabel(c.field, c.suggested)}>
                      判断のほうに直す
                    </Button>
                  </Stack>
                ))}
              </Alert>
            )}

            {run.llm && (
              <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1 }}>
                閾値に届かなかった {run.llm.fields.map((f) => FIELD_LABELS[f]).join('・')} を
                {run.llm.backend ? ' LLM に確認させました。' : ' LLM が使えないため、人の確認に回しました。'}
                {run.llm.error ? `(LLM エラー: ${run.llm.error})` : ''}
              </Typography>
            )}

            {run.escalation && !run.escalation.needed && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                CAPA へは進めません
                {run.escalation.existing_capa > 0
                  ? `(すでに CAPA が ${run.escalation.existing_capa} 件あります)`
                  : '(客先流出・再発のおそれ+重要度 高 のどちらにも当たらない)'}
              </Typography>
            )}

            {run.capa_draft && (
              <Box sx={{ mt: 2 }}>
                <Divider sx={{ mb: 1.5 }} />
                <Typography sx={{ fontWeight: 700 }}>CAPA が要る可能性があります</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  理由: {run.escalation?.reasons.join('/')}。処置案は
                  {run.capa_draft.ai_backend === 'opencode' ? ' LLM ' : '類似事例の対策 '}
                  が下書きし、各案が原因に対応しているかを Jev が確かめました。
                </Typography>
                <Stack spacing={0.5}>
                  {run.capa_draft.actions.map((a, i) => (
                    <FormControlLabel
                      key={i}
                      disabled={run.status !== 'waiting_approval'}
                      control={
                        <Checkbox
                          size="small"
                          checked={selected.includes(i)}
                          onChange={(e) =>
                            setSelected((s) => (e.target.checked ? [...s, i] : s.filter((x) => x !== i)))
                          }
                        />
                      }
                      label={
                        <Box>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                            <Chip size="small" label={a.action_type === 'preventive' ? '予防' : '是正'} />
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {a.title}
                            </Typography>
                            {a.jev_checks
                              ? (Object.entries(CAPA_CHECK_LABELS) as [keyof typeof CAPA_CHECK_LABELS, string][]).map(([k, label]) => (
                                  <Chip
                                    key={k}
                                    size="small"
                                    variant="outlined"
                                    color={a.jev_checks![k] >= 0.7 ? 'success' : 'warning'}
                                    label={`${label} ${(a.jev_checks![k] * 100).toFixed(0)}%`}
                                  />
                                ))
                              : a.jev_fits_cause !== undefined && (
                                  <Chip
                                    size="small"
                                    variant="outlined"
                                    color={a.jev_fits_cause >= 0.7 ? 'success' : 'warning'}
                                    label={`原因への対応 ${(a.jev_fits_cause * 100).toFixed(0)}%`}
                                  />
                                )}
                          </Stack>
                          <Typography variant="caption" color="text.secondary">
                            {a.description}
                          </Typography>
                        </Box>
                      }
                    />
                  ))}
                </Stack>
                {run.status === 'waiting_approval' && (
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                    <Button
                      variant="contained"
                      size="small"
                      disabled={busy || selected.length === 0}
                      onClick={() =>
                        act(
                          () => resumeTriage(run.run_id, { approved: true, selected }),
                          (r) => (r.created_capa?.length ? onCapaCreated() : undefined),
                        )
                      }
                    >
                      選んだ案を CAPA に登録
                    </Button>
                    <Button
                      size="small"
                      disabled={busy}
                      onClick={() => act(() => resumeTriage(run.run_id, { approved: false, selected: [] }))}
                    >
                      却下
                    </Button>
                  </Stack>
                )}
                {run.status === 'approved' && (run.created_capa ?? []).length > 0 && (
                  <Alert severity="success" sx={{ mt: 1 }}>
                    CAPA を登録しました: {run.created_capa!.join('、')}
                  </Alert>
                )}
              </Box>
            )}

            <Box sx={{ mt: 1.5 }}>
              <JevNotes jev={run.jev} />
              <JevFooter jev={run.jev} extra={run.run_id} />
            </Box>
          </>
        )}
      </CardContent>
    </Card>
  )
}
