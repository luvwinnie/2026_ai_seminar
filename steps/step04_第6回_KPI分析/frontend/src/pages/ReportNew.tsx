import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import SaveIcon from '@mui/icons-material/Save'
import EditNoteIcon from '@mui/icons-material/EditNote'
import PageHeader from '../components/PageHeader'
import ReportForm from '../components/ReportForm'
import { ErrorState } from '../components/StateViews'
import { createReport, ingestConfirm, ingestUpload } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { IngestUploadResponse, ReportInput } from '../types'

const ACCEPT = '.xlsx,.pdf,.png,.jpg,.jpeg'

// 手動入力の初期値(必須項目のデフォルト)
const MANUAL_DEFAULTS: ReportInput = {
  occurrence_date: new Date().toISOString().slice(0, 10),
  severity: 'medium',
  status: 'open',
  has_procedure: true,
  is_recurrence: false,
  production_count: 1,
  defect_count: 1,
}

const CONFIDENCE_COLOR: Record<string, 'success' | 'warning' | 'error'> = {
  high: 'success',
  medium: 'warning',
  low: 'error',
}

export default function ReportNew() {
  const navigate = useNavigate()
  const [tab, setTab] = useState(0)

  return (
    <Box>
      <PageHeader title="不適合報告書 新規作成" subtitle="帳票ファイルからのAI抽出、または手動入力で登録" />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab icon={<UploadFileIcon />} iconPosition="start" label="ファイルから作成 (AI抽出)" />
        <Tab icon={<EditNoteIcon />} iconPosition="start" label="手動入力" />
      </Tabs>

      {tab === 0 && <FileTab onSaved={(id) => navigate(`/reports/${id}`)} />}
      {tab === 1 && <ManualTab onSaved={(id) => navigate(`/reports/${id}`)} />}
    </Box>
  )
}

function FileTab({ onSaved }: { onSaved: (defectId: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<IngestUploadResponse | null>(null)
  const [draft, setDraft] = useState<ReportInput>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleFile = async (file: File) => {
    setUploading(true)
    setError(null)
    setResult(null)
    try {
      const res = await ingestUpload(file)
      setResult(res)
      setDraft(res.extracted)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setUploading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const created = await ingestConfirm(draft)
      onSaved(created.defect_id)
    } catch (e) {
      setError(errorMessage(e))
      setSaving(false)
    }
  }

  return (
    <Box>
      <Card
        sx={{
          mb: 2,
          border: '2px dashed #cbd5e1',
          bgcolor: '#f8fafc',
          cursor: 'pointer',
          transition: 'border-color .2s',
          '&:hover': { borderColor: 'primary.main' },
        }}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const f = e.dataTransfer.files?.[0]
          if (f) handleFile(f)
        }}
      >
        <CardContent sx={{ textAlign: 'center', py: 5 }}>
          <UploadFileIcon sx={{ fontSize: 48, color: 'primary.main', mb: 1 }} />
          <Typography sx={{ fontWeight: 700 }}>
            帳票ファイルをドロップ、またはクリックして選択
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            対応形式: Excel (.xlsx) / PDF / 画像 (.png .jpg)。AIが項目を自動抽出します。
          </Typography>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
              e.target.value = ''
            }}
          />
        </CardContent>
      </Card>

      {uploading && (
        <Alert severity="info" sx={{ mb: 2 }}>
          AIが帳票を解析しています…
        </Alert>
      )}
      {error && <ErrorState message={error} />}

      {result && (
        <Card>
          <CardContent>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 2 }}>
              <Typography sx={{ fontWeight: 700 }}>抽出結果</Typography>
              <Chip size="small" label={`ファイル: ${result.source_filename}`} variant="outlined" />
              <Chip
                size="small"
                label={`確信度: ${result.confidence}`}
                color={CONFIDENCE_COLOR[result.confidence] ?? 'default'}
              />
            </Stack>

            {result.warnings.length > 0 && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                <Typography sx={{ fontWeight: 700 }}>確認事項</Typography>
                <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {result.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </Alert>
            )}

            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              内容を確認・修正して保存してください。
            </Typography>

            <ReportForm value={draft} onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))} />

            <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
                {saving ? '保存中…' : 'この内容で保存'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  )
}

function ManualTab({ onSaved }: { onSaved: (defectId: string) => void }) {
  const [draft, setDraft] = useState<ReportInput>(MANUAL_DEFAULTS)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    // 主要な必須項目の簡易チェック
    const missing: string[] = []
    if (!draft.occurrence_date) missing.push('発生日')
    if (!draft.customer) missing.push('客先')
    if (!draft.process) missing.push('発生工程')
    if (!draft.machine_name) missing.push('使用機械')
    if (!draft.operator_name) missing.push('作業者名')
    if (!draft.part_name) missing.push('部品名称')
    if (!draft.phenomenon) missing.push('現象分類')
    if (!draft.defect_description) missing.push('不具合内容')
    if (missing.length > 0) {
      setError(`必須項目が未入力です: ${missing.join('、')}`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const created = await createReport(draft)
      onSaved(created.defect_id)
    } catch (e) {
      setError(errorMessage(e))
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardContent>
        {error && <ErrorState message={error} />}
        <ReportForm value={draft} onChange={(patch) => setDraft((d) => ({ ...d, ...patch }))} />
        <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
          <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
            {saving ? '保存中…' : '登録する'}
          </Button>
        </Box>
      </CardContent>
    </Card>
  )
}
