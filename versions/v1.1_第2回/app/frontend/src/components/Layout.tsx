import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Box, Chip, Drawer, List, ListItemButton, ListItemText, ListSubheader, Typography } from '@mui/material'
import { useTheme } from '@mui/material/styles'
import { getHealth } from '../api'

const DRAWER_WIDTH = 264

// 状態のバッジ。GET /health を開いたときに1回読む
function HealthBadge() {
  const [label, setLabel] = useState<string | null>(null)
  const [connected, setConnected] = useState(true)

  useEffect(() => {
    getHealth()
      .then((health) => setLabel(`${health.reports}件`))
      .catch(() => {
        setConnected(false)
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
      color={connected ? 'default' : 'primary'}
    />
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
          <ListItemButton
            component={NavLink}
            to="/reports"
            sx={{
              borderLeft: '3px solid transparent',
              '&.active': {
                borderLeftColor: theme.palette.primary.main,
                color: theme.palette.primary.main,
              },
            }}
          >
            <ListItemText primary="一覧" />
          </ListItemButton>
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
