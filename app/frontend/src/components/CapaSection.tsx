/**
 * CAPAセクション(docs/10 A-3) — 報告書詳細での処置管理 + AIドラフト + 8Dレポート生成。
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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedIn'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import DescriptionIcon from '@mui/icons-material/Description'
import AddIcon from '@mui/icons-material/Add'
import MarkdownMessage from './MarkdownMessage'
import {
  createCapa,
  draftCapa,
  fetchCapaList,
  generateEightD,
  updateCapa,
} from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { CapaAction, CapaDraftItem } from '../types'
import { CAPA_STATUS_LABELS } from '../pages/Capa'

export default function CapaSection({ defectId }: { defectId: string }) {
  const [items, setItems] = useState<CapaAction[]>([])
  const [error, setError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<CapaDraftItem[] | null>(null)
  const [drafting, setDrafting] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', action_type: 'corrective', owner: '', due_date: '' })
  const [eightD, setEightD] = useState<string | null>(null)
  const [gen8d, setGen8d] = useState(false)

  const reload = useCallback(() => {
    fetchCapaList({ defect_id: defectId }).then((d) => setItems(d.items)).catch(() => undefined)
  }, [defectId])
  useEffect(() => reload(), [reload])

  const runDraft = async () => {
    setDrafting(true)
    setError(null)
    try {
      const d = await draftCapa(defectId)
      setDrafts(d.actions)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setDrafting(false)
    }
  }

  const adoptDraft = async (d: CapaDraftItem) => {
    try {
      await createCapa({ defect_id: defectId, title: d.title, description: d.description, action_type: d.action_type })
      setDrafts((prev) => (prev ?? []).filter((x) => x !== d))
      reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const submitAdd = async () => {
    try {
      await createCapa({
        defect_id: defectId,
        title: form.title,
        description: form.description || undefined,
        action_type: form.action_type,
        owner: form.owner || undefined,
        due_date: form.due_date || undefined,
      })
      setAddOpen(false)
      setForm({ title: '', description: '', action_type: 'corrective', owner: '', due_date: '' })
      reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const changeStatus = async (a: CapaAction, next: string) => {
    try {
      let effect_note: string | undefined
      if (next === 'closed') {
        const note = window.prompt('効果確認メモ(closedに必須)', a.effect_note ?? '')
        if (note === null) return
        effect_note = note || '効果確認済み'
      }
      await updateCapa(a.capa_id, { status: next, effect_note } as Partial<CapaAction>)
      reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  const run8d = async () => {
    setGen8d(true)
    setError(null)
    try {
      const rep = await generateEightD(defectId)
      setEightD(rep.content_md)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setGen8d(false)
    }
  }

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
          <AssignmentTurnedInIcon color="primary" fontSize="small" />
          <Typography sx={{ fontWeight: 700, flex: 1 }}>是正・予防処置(CAPA)</Typography>
          <Button size="small" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>
            起票
          </Button>
          <Button
            size="small"
            startIcon={drafting ? <CircularProgress size={14} /> : <AutoAwesomeIcon />}
            onClick={runDraft}
            disabled={drafting}
          >
            AIドラフト
          </Button>
          <Button
            size="small"
            startIcon={gen8d ? <CircularProgress size={14} /> : <DescriptionIcon />}
            onClick={run8d}
            disabled={gen8d}
          >
            8Dレポート生成
          </Button>
        </Stack>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}

        {items.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            処置は未登録です。「AIドラフト」で類似事例に基づく案を出せます。
          </Typography>
        ) : (
          <Stack divider={<Divider />} spacing={1}>
            {items.map((a) => (
              <Stack key={a.capa_id} direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Typography sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{a.capa_id}</Typography>
                <Chip size="small" variant="outlined" label={a.action_type === 'preventive' ? '予防' : '是正'} />
                <Typography variant="body2" sx={{ flex: 1, minWidth: 200 }}>{a.title}</Typography>
                {a.overdue && <Chip size="small" color="error" label="期限超過" />}
                <TextField
                  select
                  size="small"
                  variant="standard"
                  value={a.status}
                  onChange={(e) => changeStatus(a, e.target.value)}
                  sx={{ minWidth: 110 }}
                >
                  {Object.entries(CAPA_STATUS_LABELS).map(([v, l]) => (
                    <MenuItem key={v} value={v}>{l}</MenuItem>
                  ))}
                </TextField>
              </Stack>
            ))}
          </Stack>
        )}

        {drafts && (
          <Box sx={{ mt: 2, p: 1.5, borderRadius: 2, bgcolor: 'action.hover' }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              AIドラフト(採用ボタンで登録。編集は登録後に一覧から)
            </Typography>
            {drafts.length === 0 && (
              <Typography variant="body2" color="text.secondary">提案できる処置がありません</Typography>
            )}
            <Stack spacing={1}>
              {drafts.map((d, i) => (
                <Stack key={i} direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                  <Chip size="small" variant="outlined" label={d.action_type === 'preventive' ? '予防' : '是正'} />
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>{d.title}</Typography>
                    <Typography variant="caption" color="text.secondary">{d.description}</Typography>
                  </Box>
                  <Button size="small" variant="outlined" onClick={() => adoptDraft(d)}>採用</Button>
                </Stack>
              ))}
            </Stack>
          </Box>
        )}
      </CardContent>

      {/* 起票ダイアログ */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>CAPAを起票</DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: '8px !important' }}>
          <TextField label="処置の要約(必須)" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} size="small" />
          <TextField label="詳細" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} size="small" multiline rows={3} />
          <Stack direction="row" spacing={2}>
            <TextField select label="種別" value={form.action_type} onChange={(e) => setForm({ ...form, action_type: e.target.value })} size="small" sx={{ width: 140 }}>
              <MenuItem value="corrective">是正</MenuItem>
              <MenuItem value="preventive">予防</MenuItem>
            </TextField>
            <TextField label="担当" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} size="small" />
            <TextField type="date" label="期限" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} size="small" slotProps={{ inputLabel: { shrink: true } }} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={submitAdd} disabled={!form.title.trim()}>登録</Button>
        </DialogActions>
      </Dialog>

      {/* 8Dレポートダイアログ */}
      <Dialog open={eightD !== null} onClose={() => setEightD(null)} maxWidth="md" fullWidth>
        <DialogTitle>8Dレポート</DialogTitle>
        <DialogContent dividers>{eightD && <MarkdownMessage text={eightD} />}</DialogContent>
        <DialogActions>
          <Button onClick={() => eightD && navigator.clipboard?.writeText(eightD)}>Markdownをコピー</Button>
          <Button variant="contained" onClick={() => setEightD(null)}>閉じる</Button>
        </DialogActions>
      </Dialog>
    </Card>
  )
}
