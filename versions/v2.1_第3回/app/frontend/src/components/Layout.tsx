import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Box, Chip, Drawer, List, ListItemButton, ListItemText, ListSubheader, Typography } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { getHealth } from '../api'

const DRAWER_WIDTH = 264

// 状態のバッジ。GET /health を開いたときに1回読む
function HealthBadge() {
  const [label, setLabel] = useState<string | null>(null)
  const [warning, setWarning] = useState(false)

  useEffect(() => {
    getHealth()
      .then((health) => {
        const ai = health.chat_backend === 'opencode' ? 'AI: OpenCode' : 'AI 未設定'
        setLabel(`${health.reports}件 · ${ai}`)
        setWarning(health.chat_backend !== 'opencode')
      })
      .catch(() => {
        setWarning(true)
        setLabel('バックエンド未接続')
      })
  }, [])

  if (label === null) return <Chip size="small" label="確認中…" variant="outlined" />
  return (
    <Chip
      data-testid="health-badge"
      size="small"
      label={label}
      variant="outlined"
      color={warning ? 'primary' : 'default'}  // 「AI 未設定」「バックエンド未接続」はアクセント色（注意）で出す
    />
  )
}

// 開いている項目は、左端のアクセント色の縦線と文字色で示す
function MenuItem({ to, label }: { to: string; label: string }) {
  const theme = useTheme()
  return (
    <ListItemButton
      component={NavLink}
      to={to}
      sx={{
        borderLeft: '3px solid transparent',
        '&.active': {
          borderLeftColor: theme.palette.primary.main,
          color: theme.palette.primary.main,
        },
      }}
    >
      <ListItemText primary={label} />
    </ListItemButton>
  )
}

export default function Layout() {
  const theme = useTheme()

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
            bgcolor: theme.palette.sidebar.bg,
            borderRight: `1px solid ${theme.palette.divider}`,
          },
        }}
      >
        <Box sx={{ p: 2.5 }}>
          <Typography variant="h6" sx={{ mb: 1, fontWeight: 700 }}>
            DefectReport AI
          </Typography>
          <HealthBadge />
        </Box>
        <List subheader={<ListSubheader sx={{ bgcolor: 'transparent' }}>不適合報告書</ListSubheader>}>
          <MenuItem to="/reports" label="一覧" />
        </List>
        {/* 第3回は /chat だけ（AI パネルの「アシスタント」は後の回） */}
        <List subheader={<ListSubheader sx={{ bgcolor: 'transparent' }}>AI</ListSubheader>}>
          <MenuItem to="/chat" label="チャット(全画面)" />
        </List>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: 3 }}>
        <Box sx={{ maxWidth: 1400, mx: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}
