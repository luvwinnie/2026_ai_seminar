import { useEffect, useState } from 'react'
import { Link as RouterLink, useSearchParams } from 'react-router-dom'
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card, CardContent,
  Chip, Divider, FormControlLabel, Checkbox, Link, MenuItem, Stack, Tab, Tabs, TextField, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import PageHeader from '../components/PageHeader'
import { client, errorMessage } from '../api/client'
import OntologyGraph from '../components/OntologyGraph'

type Entity = { object_type: string; object_id: string; label: string; properties: Record<string, unknown> }
type Definition = {
  version: string
  objects: Record<string, { label: string; meaning: string; identity: string; source: string; properties: Record<string, string> }>
  relations: { name: string; from: string; to: string; meaning: string; inverse: string; cardinality: string }[]
  metrics: Record<string, { label: string; unit: string; formula: string; meaning: string }>
  actions: Record<string, { rules: string[] }>
}
type Result = {
  metrics: Record<string, number | string | null>
  objects: Entity[]; total: number; next_offset: number | null; quality: string[]
  provenance: { retrieved_at: string; aggregation: string }
  scope: Record<string, unknown>
}
type Links = { source_object: Entity; objects: Entity[]; total: number; next_offset: number | null; quality: string[] }

export default function Ontology() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [definition, setDefinition] = useState<Definition | null>(null)
  const tab = searchParams.get('view') === 'graph' ? 2 : searchParams.get('view') === 'definition' ? 1 : 0
  const [result, setResult] = useState<Result | null>(null)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('MachineLabel')
  const [candidates, setCandidates] = useState<Entity[]>([])
  const [resolved, setResolved] = useState(false)
  const [selection, setSelection] = useState<Entity | null>(null)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [onlyOpen, setOnlyOpen] = useState(false)
  const [links, setLinks] = useState<Links | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resolveNote, setResolveNote] = useState('')
  const [preview, setPreview] = useState<string>('')
  const [capaId, setCapaId] = useState('')
  const [effectNote, setEffectNote] = useState('')

  useEffect(() => {
    let alive = true
    Promise.all([client.get<Definition>('/api/ontology/definition'), client.post<Result>('/api/ontology/query', {})])
      .then(([d, q]) => { if (alive) { setDefinition(d.data); setResult(q.data) } })
      .catch(e => { if (alive) setError(errorMessage(e)) })
    return () => { alive = false }
  }, [])

  async function resolveName() {
    setBusy(true); setError(''); setSelection(null); setResolved(false); setResolveNote(''); setCandidates([])
    try {
      const { data } = await client.get<{ candidates: Entity[]; total: number; can_auto_select: boolean }>('/api/ontology/resolve', { params: { object_type: kind, query: name, limit: 100 } })
      setCandidates(data.candidates); setResolved(true)
      if (data.can_auto_select) setSelection(data.candidates[0])
      setResolveNote(data.total === 0 ? '該当する名前はありません。指定条件の照会は実行していません。'
        : data.can_auto_select ? '名前が一致しました。期間などを指定して照会できます。'
        : `${data.total}件の候補があります。対象を選んでください。${data.total > 100 ? '先頭100件を表示しています。検索語を詳しくしてください。' : ''}`)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  async function query(offset = 0, scopeOverride?: Record<string, unknown>) {
    setBusy(true); setError(''); setLinks(null); setPreview('')
    const scope: Record<string, unknown> = {}
    if (selection) scope[({ MachineLabel: 'machine_id', Process: 'process_id', Customer: 'customer_id' } as Record<string, string>)[selection.object_type]] = selection.object_id
    if (start) scope.date_from = start
    if (end) scope.date_to = end
    if (onlyOpen) scope.has_open_capa = true
    try {
      const { data } = await client.post<Result>('/api/ontology/query', { scope: scopeOverride ?? scope, offset })
      setResult(data)
    } catch (e) { setResult(null); setError(errorMessage(e)) } finally { setBusy(false) }
  }

  async function related(report: Entity, offset = 0) {
    setBusy(true); setError(''); setPreview(''); setCapaId('')
    try {
      const { data } = await client.get<Links>(`/api/ontology/objects/DefectReport/${encodeURIComponent(report.object_id)}/relations/has_capa`, { params: { offset } })
      setLinks(data)
    } catch (e) { setLinks(null); setError(errorMessage(e)) } finally { setBusy(false) }
  }

  async function checkClose() {
    setBusy(true); setError(''); setPreview('')
    try {
      const { data } = await client.post<{ valid: boolean; saved: boolean; errors: string[] }>('/api/ontology/actions/capa/preview', {
        capa_id: capaId, status: 'closed', effect_note: effectNote,
      })
      setPreview(data.valid ? '入力条件を満たしています。保存は行っていません。効果の実証・承認は別途必要です。'
        : `更新できません：${data.errors.join(' / ')}`)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return <>
    <PageHeader title="業務Ontology" subtitle="対象の意味を確かめ、報告書から関連する処置と根拠をたどる" />
    <Tabs value={tab} onChange={(_, value) => setSearchParams(value === 2 ? { view: 'graph' } : value === 1 ? { view: 'definition' } : {})} variant="scrollable" scrollButtons="auto" sx={{ mb: 3 }}>
      <Tab label="実データを調べる" /><Tab label="定義と計算方法" /><Tab label="グラフで見る" />
    </Tabs>
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    {tab === 2 && definition && <OntologyGraph definition={definition} reportIds={result?.objects.map(o => o.object_id) ?? []} />}
    {tab === 0 && <Stack spacing={3}>
      <Card><CardContent><Stack spacing={2}>
        <Typography variant="h6">1. 対象と期間を指定する</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField select label="対象の種類" value={kind} disabled={busy} sx={{ minWidth: 140 }} onChange={e => { setKind(e.target.value); setSelection(null); setCandidates([]); setResolved(false); setResolveNote('') }}>
            <MenuItem value="MachineLabel">機械名</MenuItem><MenuItem value="Process">工程名</MenuItem><MenuItem value="Customer">顧客名</MenuItem>
          </TextField>
          <TextField label="名前を検索" value={name} disabled={busy} onChange={e => { setName(e.target.value); setSelection(null); setResolved(false); setCandidates([]); setResolveNote('') }} fullWidth />
          <Button onClick={resolveName} disabled={!name.trim() || busy} sx={{ flexShrink: 0 }}>名前を確認</Button>
        </Stack>
        {resolveNote && <Alert severity="info">{resolveNote}</Alert>}
        {resolved && candidates.length > 0 && <TextField select label="照会する対象" value={selection?.object_id ?? ''} disabled={busy} onChange={e => setSelection(candidates.find(c => c.object_id === e.target.value) ?? null)}>
          {candidates.map(c => <MenuItem key={c.object_id} value={c.object_id}>{c.label}</MenuItem>)}
        </TextField>}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField label="発生日（開始）" type="date" value={start} onChange={e => setStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="発生日（終了）" type="date" value={end} onChange={e => setEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <FormControlLabel control={<Checkbox checked={onlyOpen} onChange={e => setOnlyOpen(e.target.checked)} />} label="未クローズCAPAがある報告" />
        </Stack>
        <Stack direction="row" spacing={2}>
          <Button variant="contained" disabled={busy || (!!name.trim() && !selection)} onClick={() => query()}>条件で照会</Button>
          <Button disabled={busy} onClick={() => { setName(''); setSelection(null); setCandidates([]); setResolveNote(''); setStart(''); setEnd(''); setOnlyOpen(false); query(0, {}) }}>全報告を照会</Button>
        </Stack>
        <Typography variant="body2" color="text.secondary">機械名は報告に記録された名称です。設備個体や工場を識別するものではありません。</Typography>
      </Stack></CardContent></Card>
      {result && <Card><CardContent><Stack spacing={2}>
        <Typography variant="h6">2. 該当する報告と指標</Typography>
        <Typography variant="body2" color="text.secondary">以下は前回実行した照会結果です。条件を変更した後は「条件で照会」を押してください。</Typography>
        <Stack direction="row" sx={{ gap: 2, flexWrap: 'wrap' }}>
          {[['report_count', '報告件数', '件'], ['defect_units', '記録不適合数', '個'], ['known_loss_jpy', '既知の損失額', '円'], ['open_capa_count', '未クローズCAPA', '件']].map(([key, label, unit]) =>
            <Box key={key} sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 1, minWidth: 145 }}>
              <Typography variant="body2" color="text.secondary">{label}</Typography>
              <Typography variant="h5">{result.metrics[key] == null ? '不明' : `${Number(result.metrics[key]).toLocaleString()} ${unit}`}</Typography>
            </Box>)}
        </Stack>
        <Typography>記録上の不適合率：{result.metrics.recorded_defect_rate == null ? '算出不可' : `${(Number(result.metrics.recorded_defect_rate) * 100).toFixed(2)}%`}（工場全体の不良率ではありません）</Typography>
        {result.quality.map(q => <Alert severity="warning" key={q}>{q}</Alert>)}
        <Typography variant="body2">全{result.total}件のうち、このページに{result.objects.length}件を表示。集計は全該当報告を対象とします。</Typography>
        {result.objects.map(o => <Box key={o.object_id} sx={{ py: 1, borderBottom: 1, borderColor: 'divider' }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ justifyContent: 'space-between', gap: 1 }}>
            <Box><Link component={RouterLink} to={`/reports/${o.object_id}`}>{o.label}</Link>
              <Typography variant="body2" color="text.secondary">{String(o.properties.machine_name)} / {String(o.properties.process)} / {String(o.properties.occurrence_date)}</Typography></Box>
            <Button disabled={busy} onClick={() => related(o)}>関連CAPAをたどる</Button>
          </Stack>
        </Box>)}
        <Stack direction="row" spacing={2}>
          <Button disabled={busy} onClick={() => query(0, result.scope)}>先頭へ</Button>
          {result.next_offset !== null && <Button disabled={busy} onClick={() => query(result.next_offset!, result.scope)}>次の報告</Button>}
        </Stack>
        <Typography variant="caption" color="text.secondary">取得：{new Date(result.provenance.retrieved_at).toLocaleString('ja-JP')} ／ 定義 v{definition?.version}</Typography>
      </Stack></CardContent></Card>}
      {links && <Card><CardContent><Stack spacing={2}>
        <Typography variant="h6">3. {links.source_object.object_id} → 是正・予防処置</Typography>
        <Typography>{links.total}件の関連CAPA。報告書IDが一致する処置を表示しています。</Typography>
        {links.quality.map(q => <Alert key={q} severity="warning">{q}</Alert>)}
        {links.objects.map(o => <Box key={o.object_id}>
          <Typography>{o.object_id}：{o.label} <Chip size="small" label={String(o.properties.status)} /></Typography>
          <Button onClick={() => { setCapaId(o.object_id); setEffectNote(String(o.properties.effect_note ?? '')); setPreview('') }}>クローズ条件を検証</Button>
        </Box>)}
        {links.next_offset !== null && <Button disabled={busy} onClick={() => related(links.source_object, links.next_offset!)}>次のCAPA</Button>}
        {capaId && <><Divider /><Typography>{capaId} の更新プレビュー（保存しません）</Typography>
          <TextField label="効果確認メモ" multiline minRows={2} value={effectNote} onChange={e => setEffectNote(e.target.value)} />
          <Button disabled={busy} onClick={checkClose}>closedへの変更を検証</Button>
          {preview && <Alert severity="info">{preview}</Alert>}
          <Link component={RouterLink} to="/capa">是正処置の管理画面へ</Link>
        </>}
      </Stack></CardContent></Card>}
    </Stack>}
    {tab === 1 && definition && <Stack spacing={2}>
      <Typography variant="h6">対象と関係</Typography>
      {definition.relations.map(r => <Card key={r.name}><CardContent>
        <Stack direction="row" sx={{ alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Chip label={definition.objects[r.from].label} variant="outlined" /><Typography>→ {r.name} →</Typography><Chip label={definition.objects[r.to].label} variant="outlined" />
        </Stack><Typography sx={{ mt: 1 }}>{r.meaning}</Typography>
        <Typography variant="caption" color="text.secondary">{r.cardinality} ／ 逆方向：{r.inverse}</Typography>
      </CardContent></Card>)}
      {Object.entries(definition.objects).map(([key, o]) => <Accordion key={key}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>{o.label}（{key}）の定義</AccordionSummary>
        <AccordionDetails><Stack spacing={1}><Typography>{o.meaning}</Typography><Typography>ID：{o.identity}</Typography>
          <Typography>データ元：{o.source}</Typography>{Object.entries(o.properties).map(([k, v]) => <Typography key={k}>{k}：{v}</Typography>)}
        </Stack></AccordionDetails>
      </Accordion>)}
      <Typography variant="h6" sx={{ pt: 2 }}>指標の計算方法</Typography>
      {Object.entries(definition.metrics).map(([key, m]) => <Card key={key}><CardContent>
        <Typography variant="subtitle1">{m.label}（{m.unit}）</Typography>
        <Typography component="code" sx={{ display: 'block', my: 1, overflowWrap: 'anywhere' }}>{m.formula}</Typography><Typography>{m.meaning}</Typography>
      </CardContent></Card>)}
      <Typography variant="h6">処置を変更するときのルール</Typography>
      {definition.actions.update_capa_action.rules.map(r => <Typography key={r}>・{r}</Typography>)}
    </Stack>}
  </>
}
