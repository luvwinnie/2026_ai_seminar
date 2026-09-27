import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Paper,
  Snackbar,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import EditIcon from '@mui/icons-material/Edit'
import DeleteIcon from '@mui/icons-material/Delete'
import PageHeader from '../components/PageHeader'
import { Loading, ErrorState, EmptyState } from '../components/StateViews'
import { useMasters } from '../hooks/useMasters'
import { createMaster, deleteMaster, updateMaster } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { MasterCategory, MasterItem } from '../types'
import { MASTER_CATEGORIES, MASTER_CATEGORY_LABELS } from '../constants/masters'
import { formatNumber } from '../utils/format'

export default function Masters() {
  const { data, loading, error, reload } = useMasters()
  const [category, setCategory] = useState<MasterCategory>('customer')

  // 追加入力
  const [newName, setNewName] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // 編集ダイアログ
  const [editing, setEditing] = useState<MasterItem | null>(null)
  const [editName, setEditName] = useState('')

  // 削除確認
  const [deleting, setDeleting] = useState<MasterItem | null>(null)

  // 完了通知
  const [snack, setSnack] = useState<string | null>(null)

  const label = MASTER_CATEGORY_LABELS[category]
  const rows = data?.[category] ?? []

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    setActionError(null)
    try {
      await createMaster(category, name)
      setNewName('')
      reload()
      setSnack(`「${name}」を追加しました`)
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const handleToggleActive = async (item: MasterItem, next: boolean) => {
    setBusy(true)
    setActionError(null)
    try {
      await updateMaster(category, item.id, { is_active: next })
      reload()
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const openEdit = (item: MasterItem) => {
    setEditing(item)
    setEditName(item.name)
    setActionError(null)
  }

  const handleRename = async () => {
    if (!editing) return
    const name = editName.trim()
    if (!name || name === editing.name) {
      setEditing(null)
      return
    }
    setBusy(true)
    setActionError(null)
    try {
      const result = await updateMaster(category, editing.id, { name })
      setEditing(null)
      reload()
      setSnack(
        result.updated_reports > 0
          ? `「${name}」に変更。報告書 ${formatNumber(result.updated_reports)} 件の表記も更新しました`
          : `「${name}」に変更しました`,
      )
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    if (!deleting) return
    setBusy(true)
    setActionError(null)
    try {
      await deleteMaster(category, deleting.id)
      setDeleting(null)
      reload()
      setSnack('削除しました')
    } catch (e) {
      setActionError(errorMessage(e))
      setDeleting(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box>
      <PageHeader
        title="マスタ管理"
        subtitle="ドロップダウンの選択肢(客先・工程・機械・作業者・現象・要因)を編集します"
      />

      <Tabs
        value={category}
        onChange={(_, v) => {
          setCategory(v)
          setActionError(null)
          setNewName('')
        }}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2 }}
      >
        {MASTER_CATEGORIES.map((c) => (
          <Tab key={c} value={c} label={MASTER_CATEGORY_LABELS[c]} />
        ))}
      </Tabs>

      {loading && <Loading />}
      {error && <ErrorState message={error} />}

      {!loading && !error && data && (
        <>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                新しい選択肢を追加({label})
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                <TextField
                  size="small"
                  placeholder={`${label}の名称`}
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAdd()
                  }}
                  sx={{ flex: '1 1 320px', maxWidth: 420 }}
                />
                <Button
                  variant="contained"
                  startIcon={<AddIcon />}
                  onClick={handleAdd}
                  disabled={busy || !newName.trim()}
                >
                  追加
                </Button>
              </Box>
              {actionError && (
                <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setActionError(null)}>
                  {actionError}
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card>
            <TableContainer component={Paper} elevation={0}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>名称</TableCell>
                    <TableCell align="right">使用件数</TableCell>
                    <TableCell align="center">有効</TableCell>
                    <TableCell align="center">編集</TableCell>
                    <TableCell align="center">削除</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((item) => {
                    const inUse = item.usage_count > 0
                    return (
                      <TableRow key={item.id} hover>
                        <TableCell sx={{ fontWeight: 600, opacity: item.is_active ? 1 : 0.5 }}>
                          {item.name}
                          {!item.is_active && (
                            <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                              (無効)
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell align="right">{formatNumber(item.usage_count)}</TableCell>
                        <TableCell align="center">
                          <Switch
                            size="small"
                            checked={item.is_active}
                            onChange={(e) => handleToggleActive(item, e.target.checked)}
                            disabled={busy}
                            slotProps={{ input: { 'aria-label': `${item.name} の有効/無効` } }}
                          />
                        </TableCell>
                        <TableCell align="center">
                          <IconButton size="small" onClick={() => openEdit(item)} disabled={busy} aria-label="編集">
                            <EditIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                        <TableCell align="center">
                          {inUse ? (
                            <Tooltip title="使用中のため削除不可(無効化を使用してください)">
                              {/* span で disabled ボタンにも Tooltip を効かせる */}
                              <span>
                                <IconButton size="small" disabled aria-label="削除(不可)">
                                  <DeleteIcon fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          ) : (
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => setDeleting(item)}
                              disabled={busy}
                              aria-label="削除"
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </TableContainer>
            {rows.length === 0 && <EmptyState message={`${label}のマスタがありません`} />}
          </Card>
        </>
      )}

      {/* リネームダイアログ */}
      <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} fullWidth maxWidth="xs">
        <DialogTitle>名称の変更({label})</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            label="名称"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            sx={{ mt: 1 }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename()
            }}
          />
          {editing && editing.usage_count > 0 && (
            <Alert severity="info" sx={{ mt: 2 }}>
              使用中の報告書 {formatNumber(editing.usage_count)} 件の表記も新しい名称へ書き換わります。
            </Alert>
          )}
          {actionError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {actionError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)} disabled={busy}>
            キャンセル
          </Button>
          <Button variant="contained" onClick={handleRename} disabled={busy || !editName.trim()}>
            {busy ? '更新中…' : '変更'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 削除確認 */}
      <Dialog open={Boolean(deleting)} onClose={() => setDeleting(null)} maxWidth="xs">
        <DialogTitle>選択肢を削除しますか?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {label}「{deleting?.name}」を削除します。この操作は取り消せません。
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleting(null)} disabled={busy}>
            キャンセル
          </Button>
          <Button color="error" variant="contained" onClick={handleDelete} disabled={busy}>
            {busy ? '削除中…' : '削除する'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={Boolean(snack)}
        autoHideDuration={4000}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="success" variant="filled" onClose={() => setSnack(null)}>
          {snack}
        </Alert>
      </Snackbar>
    </Box>
  )
}
