import { useEffect, useId, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Alert, Box, Button, Card, CardContent, Chip, Link, MenuItem, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography, useTheme } from '@mui/material'
import { client, errorMessage } from '../api/client'

type ObjectDefinition = { label: string; meaning: string; identity: string; properties: Record<string, string> }
type Relation = { name: string; from: string; to: string; meaning: string; cardinality: string; inverse: string }
type Definition = { objects: Record<string, ObjectDefinition>; relations: Relation[] }
type Node = { id: string; object_type: string; object_id: string; label: string; properties: Record<string, unknown>; source?: Record<string, unknown> }
type Edge = { id: string; source: string; target: string; relation: string; meaning: string; cardinality: string; evidence?: Record<string, unknown> }
type Graph = { root: string; nodes: Node[]; edges: Edge[]; relation_counts: Record<string, number>; truncated_relations: { relation: string; total: number }[]; provenance: { retrieved_at: string } }

const POSITIONS: Record<string, [number, number]> = {
  DefectReport: [480, 300], MachineLabel: [175, 95], Process: [480, 70], Customer: [785, 95], CapaAction: [480, 535],
}
const SHORT_RELATIONS: Record<string, string> = { recorded_on: '記録された機械', in_process: '記録された工程', for_customer: '記録された顧客', has_capa: '是正・予防処置' }
const short = (text: string, max = 20) => text.length > max ? text.slice(0, max - 1) + '…' : text

export default function OntologyGraph({ definition, reportIds }: { definition: Definition; reportIds: string[] }) {
  const theme = useTheme()
  const markerId = useId().replace(/:/g, '')
  const [mode, setMode] = useState<'schema' | 'data'>('schema')
  const [reportId, setReportId] = useState(reportIds[0] ?? '')
  const [graph, setGraph] = useState<Graph | null>(null)
  const [selectedId, setSelectedId] = useState('DefectReport')
  const [error, setError] = useState('')
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (mode !== 'data' || !reportId) return
    let alive = true
    setLoading(true); setError(''); setGraph(null)
    client.get<Graph>(`/api/ontology/graph/${encodeURIComponent(reportId)}`)
      .then(({ data }) => { if (alive) { setGraph(data); setSelectedId(data.root) } })
      .catch(e => { if (alive) setError(errorMessage(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [mode, reportId])

  const nodes: Node[] = mode === 'schema' ? Object.entries(definition.objects).map(([type, d]) => ({
    id: type, object_type: type, object_id: type, label: d.label, properties: {},
  })) : graph?.nodes ?? []
  const edges: Edge[] = mode === 'schema' ? definition.relations.map(r => ({
    id: r.name, source: r.from, target: r.to, relation: r.name, meaning: r.meaning, cardinality: r.cardinality,
  })) : graph?.edges ?? []
  const selected = nodes.find(n => n.id === selectedId)
  const capaNodes = nodes.filter(n => n.object_type === 'CapaAction')
  // CAPAが複数ある場合は専用行へ配置。辺の根拠は選択ノードの詳細に表示。
  const positions = new Map(nodes.map(n => {
    const i = capaNodes.indexOf(n)
    return [n.id, n.object_type === 'CapaAction' && capaNodes.length > 1
      ? [175 + (i % 3) * 305, 535 + Math.floor(i / 3) * 115] as [number, number]
      : POSITIONS[n.object_type]]
  }))
  const height = mode === 'data' && capaNodes.length === 0 ? 420
    : 635 + Math.floor(Math.max(0, capaNodes.length - 1) / 3) * 115
  const dark = theme.palette.mode === 'dark'
  const line = dark ? '#91a5b6' : '#657b8b'
  const nodeFill = dark ? '#263540' : '#f0f4f6'
  const activeFill = dark ? '#3d5669' : '#dce7ee'
  const ink = theme.palette.text.primary

  return <Stack spacing={2}>
    <Typography variant="h6">Ontologyのグラフ</Typography>
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      <ToggleButtonGroup exclusive value={mode} size="small" onChange={(_, value) => { if (value) { setMode(value); setSelectedId(value === 'schema' ? 'DefectReport' : ''); setZoom(1) } }} aria-label="グラフの種類">
        <ToggleButton value="schema">構造（型と関係）</ToggleButton><ToggleButton value="data">実データの関係</ToggleButton>
      </ToggleButtonGroup>
      {mode === 'data' && <TextField select size="small" label="中心となる報告書" value={reportId} onChange={e => setReportId(e.target.value)} sx={{ minWidth: 190 }}>
        {reportIds.map(id => <MenuItem key={id} value={id}>{id}</MenuItem>)}
      </TextField>}
    </Stack>
    <Typography color="text.secondary">{mode === 'schema'
      ? '5種類の対象と4種類の関係を表示しています。矢印の向きと、1対多・多対1の対応を確認できます。'
      : '「実データを調べる」の照会結果から報告書を選び、DBに記録された関係を表示します。線は類似度や因果関係を表しません。'}</Typography>
    {mode === 'data' && !reportIds.length && <Alert severity="info">照会結果に報告書がありません。「実データを調べる」で条件を変更してください。</Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    {loading && <Typography role="status">関係を取得しています…</Typography>}
    {mode === 'data' && graph?.relation_counts.has_capa === 0 && <Alert severity="info">この報告書にはCAPAが登録されていません。CAPAのノードと線は表示していません。</Alert>}
    {mode === 'data' && graph?.truncated_relations.map(r => <Alert key={r.relation} severity="warning">{r.relation}は全{r.total}件のうち先頭50件を表示しています。処置一覧で全件を確認してください。</Alert>)}
    <Card><CardContent>
      <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
        <Button size="small" aria-label="グラフを縮小" onClick={() => setZoom(z => Math.max(0.6, z - 0.2))}>−</Button>
        <Typography variant="body2">{Math.round(zoom * 100)}%</Typography>
        <Button size="small" aria-label="グラフを拡大" onClick={() => setZoom(z => Math.min(2, z + 0.2))}>＋</Button>
        <Button size="small" onClick={() => setZoom(1)}>リセット</Button>
      </Stack>
      <Box sx={{ overflow: 'auto', maxHeight: 760, border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper' }}>
        <svg viewBox={`0 0 960 ${height}`} style={{ display: 'block', margin: 'auto', width: `${zoom * 100}%`, minWidth: 720 * zoom, height: 'auto' }} aria-label={mode === 'schema' ? 'Ontology構造グラフ' : 'Ontology実データグラフ'} role="group">
          <defs><marker id={markerId} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill={line} /></marker></defs>
          {edges.map(e => {
            const a = positions.get(e.source)!, b = positions.get(e.target)!
            const dx = b[0] - a[0], dy = b[1] - a[1]
            const from = Math.min(102 / (Math.abs(dx) || 1), 44 / (Math.abs(dy) || 1))
            const to = Math.min(110 / (Math.abs(dx) || 1), 51 / (Math.abs(dy) || 1))
            const x1 = a[0] + dx * from, y1 = a[1] + dy * from, x2 = b[0] - dx * to, y2 = b[1] - dy * to
            const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
            const active = selectedId === e.source || selectedId === e.target
            const hideLabel = mode === 'data' && e.relation === 'has_capa' && capaNodes.length > 3
            return <g key={e.id}>
              <title>{e.relation}：{e.meaning}</title>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={line} strokeWidth={active ? 2.2 : 1.3} markerEnd={`url(#${markerId})`} />
              {!hideLabel && <g><rect x={mx - 87} y={my - 27} width="174" height="54" rx="4" fill={theme.palette.background.paper} />
                <text x={mx} y={my - 8} textAnchor="middle" fill={ink} fontSize="13">{SHORT_RELATIONS[e.relation]}</text>
                <text x={mx} y={my + 9} textAnchor="middle" fill={line} fontSize="12">{e.relation}</text>
                <text x={mx} y={my + 24} textAnchor="middle" fill={line} fontSize="11">{e.cardinality === 'one-to-many' ? '1 → 多' : '多 → 1'}</text>
              </g>}
            </g>
          })}
          {nodes.map(n => {
            const [x, y] = positions.get(n.id)!
            const active = n.id === selectedId
            return <g key={n.id} transform={`translate(${x - 102}, ${y - 44})`} role="button" tabIndex={0}
              aria-label={`${definition.objects[n.object_type].label}ノード：${n.label}`} aria-pressed={active}
              onClick={() => setSelectedId(n.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedId(n.id) } }} style={{ cursor: 'pointer' }}>
              <title>{n.label}</title>
              <rect width="204" height="88" rx="8" fill={active ? activeFill : nodeFill} stroke={line} strokeWidth={active ? 2.5 : 1} />
              <text x="102" y="24" textAnchor="middle" fill={line} fontSize="12">{n.object_type}</text>
              <text x="102" y="48" textAnchor="middle" fill={ink} fontSize="15" fontWeight="600">{short(n.label, 17)}</text>
              <text x="102" y="70" textAnchor="middle" fill={line} fontSize="12">{mode === 'schema' ? (n.object_type === 'DefectReport' ? 'ID: defect_id' : n.object_type === 'CapaAction' ? 'ID: capa_id' : '報告書に記録された名称') : short(n.object_type === 'DefectReport' || n.object_type === 'CapaAction' ? n.object_id : '名称で識別する集合', 24)}</text>
            </g>
          })}
        </svg>
      </Box>
      <Typography variant="caption" color="text.secondary">ノードを選ぶと下に詳細を表示します。図はスクロール・拡大できます。配色は対象の重要度を表しません。</Typography>
    </CardContent></Card>
    {selected && <Card><CardContent><Stack spacing={1}>
      <Typography variant="h6">選択中：{selected.label}</Typography>
      <Chip size="small" label={selected.object_type} sx={{ alignSelf: 'start' }} />
      <Typography>{definition.objects[selected.object_type].meaning}</Typography>
      {mode === 'schema' ? <>
        <Typography>ID：{definition.objects[selected.object_type].identity}</Typography>
        {Object.entries(definition.objects[selected.object_type].properties).map(([k, v]) => <Typography key={k}>{k}：{v}</Typography>)}
      </> : <>
        {Object.entries(selected.properties).filter(([, v]) => v != null).map(([k, v]) => <Typography key={k} variant="body2" sx={{ overflowWrap: 'anywhere' }}>{k}：{String(v)}</Typography>)}
        {selected.object_type === 'DefectReport' && <Link component={RouterLink} to={`/reports/${selected.object_id}`}>元の報告書を開く</Link>}
        {selected.source && <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>出典：{JSON.stringify(selected.source)}</Typography>}
        <Typography variant="caption">取得：{graph && new Date(graph.provenance.retrieved_at).toLocaleString('ja-JP')}</Typography>
      </>}
      <Typography variant="subtitle2" sx={{ pt: 1 }}>接続している関係</Typography>
      {edges.filter(e => e.source === selected.id || e.target === selected.id).map(e => <Box key={e.id} sx={{ pl: 1, borderLeft: 2, borderColor: 'divider' }}>
        <Typography variant="body2">{nodes.find(n => n.id === e.source)?.label} → {e.relation} → {nodes.find(n => n.id === e.target)?.label}</Typography>
        <Typography variant="body2" color="text.secondary">{e.meaning}</Typography>
        {e.evidence && <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>関係の根拠：{JSON.stringify(e.evidence)}</Typography>}
      </Box>)}
    </Stack></CardContent></Card>}
  </Stack>
}
