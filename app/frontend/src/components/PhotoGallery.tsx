/**
 * 現場写真ギャラリー(docs/10 B-4) — 写真の添付・閲覧・削除と「AI外観アシスト」。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera'
import DeleteIcon from '@mui/icons-material/DeleteOutlineOutlined'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import { analyzePhoto, deletePhoto, fetchPhotos, uploadPhoto } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { PhotoAnalysis, ReportPhoto } from '../types'

export default function PhotoGallery({ defectId }: { defectId: string }) {
  const [items, setItems] = useState<ReportPhoto[]>([])
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [analyzing, setAnalyzing] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<Record<string, PhotoAnalysis>>({})
  const fileRef = useRef<HTMLInputElement>(null)

  const reload = useCallback(() => {
    fetchPhotos(defectId).then((d) => setItems(d.items)).catch(() => undefined)
  }, [defectId])
  useEffect(() => reload(), [reload])

  const onUpload = async (f: File | undefined) => {
    if (!f) return
    setUploading(true)
    setError(null)
    try {
      await uploadPhoto(defectId, f)
      reload()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const onAnalyze = async (name: string) => {
    setAnalyzing(name)
    setError(null)
    try {
      const res = await analyzePhoto(defectId, name)
      setAnalysis((prev) => ({ ...prev, [name]: res }))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setAnalyzing(null)
    }
  }

  const onDelete = async (name: string) => {
    if (!window.confirm('この写真を削除しますか?')) return
    try {
      await deletePhoto(defectId, name)
      reload()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5 }}>
          <PhotoCameraIcon color="primary" fontSize="small" />
          <Typography sx={{ fontWeight: 700, flex: 1 }}>現場写真</Typography>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            hidden
            onChange={(e) => onUpload(e.target.files?.[0])}
          />
          <Button
            size="small"
            startIcon={uploading ? <CircularProgress size={14} /> : <PhotoCameraIcon />}
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
          >
            写真を追加
          </Button>
        </Stack>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {items.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            写真は未添付です(スマホからもアップロードできます)
          </Typography>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 1.5 }}>
            {items.map((p) => {
              const a = analysis[p.name]
              return (
                <Box key={p.name} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
                  <Box
                    component="img"
                    src={p.url}
                    alt={p.name}
                    sx={{ width: '100%', height: 140, objectFit: 'cover', display: 'block', cursor: 'pointer' }}
                    onClick={() => window.open(p.url, '_blank')}
                  />
                  <Stack direction="row" sx={{ alignItems: 'center', px: 0.5 }}>
                    <Tooltip title="AI外観アシスト(観察所見と現象候補)">
                      <span>
                        <IconButton size="small" onClick={() => onAnalyze(p.name)} disabled={analyzing === p.name}>
                          {analyzing === p.name ? <CircularProgress size={14} /> : <AutoAwesomeIcon fontSize="small" />}
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                      {(p.size / 1024).toFixed(0)} KB
                    </Typography>
                    <IconButton size="small" onClick={() => onDelete(p.name)} aria-label="写真を削除">
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                  {a && (
                    <Box sx={{ p: 1, pt: 0 }}>
                      <Typography variant="caption" component="div">{a.observation}</Typography>
                      <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap' }}>
                        {(a.phenomenon_candidates ?? []).map((c) => (
                          <Chip key={c} size="small" variant="outlined" color="primary" label={c} />
                        ))}
                      </Stack>
                    </Box>
                  )}
                </Box>
              )
            })}
          </Box>
        )}
      </CardContent>
    </Card>
  )
}
