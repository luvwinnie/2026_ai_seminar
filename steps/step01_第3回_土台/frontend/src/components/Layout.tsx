import { Suspense, useEffect, useState } from 'react'
import { Link as RouterLink, NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Box,
  Chip,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Toolbar,
  Typography,
} from '@mui/material'
import DashboardIcon from '@mui/icons-material/Dashboard'
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive'
import DescriptionIcon from '@mui/icons-material/Description'
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutlined'
import PrecisionManufacturingIcon from '@mui/icons-material/PrecisionManufacturing'
import PersonIcon from '@mui/icons-material/Person'
import BusinessIcon from '@mui/icons-material/Business'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import ChatIcon from '@mui/icons-material/Chat'
import InsightsIcon from '@mui/icons-material/Insights'
import type { ReactNode } from 'react'
import { DRAWER_WIDTH, SIDEBAR_ACCENT, SIDEBAR_BG, SIDEBAR_SELECTED } from '../theme'
import { fetchHealth } from '../api/endpoints'
import { Loading } from './StateViews'

interface NavItem {
  label: string
  to: string
  icon: ReactNode
  // 第3回では未実装の項目。将来像として disabled 表示する。
  disabled?: boolean
}

interface NavSection {
  heading: string
  items: NavItem[]
}

// この回で有効なのは「一覧・検索」のみ。他は後の回で有効化する(将来項目として表示)。
const SECTIONS: NavSection[] = [
  {
    heading: '経営者向け',
    items: [
      { label: 'サマリー', to: '/dashboard', icon: <DashboardIcon />, disabled: true },
      { label: '予測アラート', to: '/alerts', icon: <NotificationsActiveIcon />, disabled: true },
    ],
  },
  {
    heading: '不適合報告書',
    items: [
      { label: '一覧・検索', to: '/reports', icon: <DescriptionIcon /> },
      { label: '新規作成', to: '/reports/new', icon: <AddCircleOutlineIcon />, disabled: true },
    ],
  },
  {
    heading: 'データ分析',
    items: [
      { label: '機械別', to: '/analysis/machines', icon: <PrecisionManufacturingIcon />, disabled: true },
      { label: '担当者別', to: '/analysis/operators', icon: <PersonIcon />, disabled: true },
      { label: '顧客別', to: '/analysis/customers', icon: <BusinessIcon />, disabled: true },
      { label: '時系列', to: '/analysis/trends', icon: <ShowChartIcon />, disabled: true },
    ],
  },
  {
    heading: 'AI',
    items: [{ label: 'チャット', to: '/chat', icon: <ChatIcon />, disabled: true }],
  },
]

function HealthBadge() {
  const [text, setText] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  useEffect(() => {
    let alive = true
    fetchHealth()
      .then((h) => {
        if (!alive) return
        setOk(true)
        setText(
          `${h.reports}件 · ${h.vector_search === 'e5' ? 'ベクトル検索' : 'キーワード検索'} · AI ${
            h.anthropic_configured ? '有効' : '未設定'
          }`,
        )
      })
      .catch(() => {
        if (!alive) return
        setOk(false)
        setText('バックエンド未接続')
      })
    return () => {
      alive = false
    }
  }, [])

  if (!text) return null
  return (
    <Chip
      size="small"
      label={text}
      sx={{
        bgcolor: ok ? 'rgba(37,99,235,0.18)' : 'rgba(220,38,38,0.2)',
        color: ok ? '#bfdbfe' : '#fecaca',
        fontSize: 11,
        height: 22,
      }}
    />
  )
}

export default function Layout() {
  const location = useLocation()

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
            bgcolor: SIDEBAR_BG,
            color: '#e2e8f0',
            borderRight: 'none',
          },
        }}
      >
        <Box
          component={RouterLink}
          to="/reports"
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1.5,
            px: 2.5,
            py: 2.5,
            textDecoration: 'none',
            color: 'inherit',
          }}
        >
          <InsightsIcon sx={{ color: '#38bdf8', fontSize: 30 }} />
          <Box>
            <Typography sx={{ fontWeight: 800, fontSize: 18, lineHeight: 1.1, color: '#f8fafc' }}>
              DefectReport AI
            </Typography>
            <Typography sx={{ fontSize: 11, color: '#94a3b8' }}>製造業 不良報告分析AI</Typography>
          </Box>
        </Box>

        <Box sx={{ px: 2.5, pb: 1.5 }}>
          <HealthBadge />
        </Box>

        <Box sx={{ overflowY: 'auto', flex: 1, pb: 2 }}>
          {SECTIONS.map((section) => (
            <List
              key={section.heading}
              subheader={
                <ListSubheader
                  disableSticky
                  sx={{
                    bgcolor: 'transparent',
                    color: '#64748b',
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    lineHeight: '32px',
                    textTransform: 'uppercase',
                  }}
                >
                  {section.heading}
                </ListSubheader>
              }
              sx={{ px: 1.5 }}
            >
              {section.items.map((item) => {
                // 未実装項目は非活性で「準備中」を表示する
                if (item.disabled) {
                  return (
                    <ListItemButton
                      key={item.to}
                      disabled
                      sx={{ borderRadius: 2, mb: 0.5, color: '#64748b', opacity: 0.55 }}
                    >
                      <ListItemIcon sx={{ color: '#475569', minWidth: 38 }}>{item.icon}</ListItemIcon>
                      <ListItemText
                        primary={item.label}
                        slotProps={{ primary: { sx: { fontSize: 14, fontWeight: 600 } } }}
                      />
                      <Chip
                        label="準備中"
                        size="small"
                        sx={{ height: 18, fontSize: 10, bgcolor: '#1e293b', color: '#94a3b8' }}
                      />
                    </ListItemButton>
                  )
                }
                const selected =
                  location.pathname === item.to ||
                  (item.to !== '/reports' && location.pathname.startsWith(item.to + '/'))
                return (
                  <ListItemButton
                    key={item.to}
                    component={NavLink}
                    to={item.to}
                    end={item.to === '/reports'}
                    selected={selected}
                    sx={{
                      borderRadius: 2,
                      mb: 0.5,
                      color: '#cbd5e1',
                      '& .MuiListItemIcon-root': { color: '#94a3b8', minWidth: 38 },
                      '&:hover': { bgcolor: SIDEBAR_ACCENT },
                      '&.Mui-selected, &.active': {
                        bgcolor: SIDEBAR_SELECTED,
                        color: '#fff',
                        '& .MuiListItemIcon-root': { color: '#fff' },
                        '&:hover': { bgcolor: SIDEBAR_SELECTED },
                      },
                    }}
                  >
                    <ListItemIcon>{item.icon}</ListItemIcon>
                    <ListItemText
                      primary={item.label}
                      slotProps={{ primary: { sx: { fontSize: 14, fontWeight: 600 } } }}
                    />
                  </ListItemButton>
                )
              })}
            </List>
          ))}
        </Box>

        <Box sx={{ px: 2.5, py: 2, borderTop: '1px solid #1e293b' }}>
          <Typography sx={{ fontSize: 10, color: '#64748b' }}>第3回 土台 · 2026</Typography>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, bgcolor: 'background.default' }}>
        <Toolbar sx={{ display: { xs: 'block', md: 'none' } }} />
        <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1400, mx: 'auto' }}>
          <Suspense fallback={<Loading />}>
            <Outlet />
          </Suspense>
        </Box>
      </Box>
    </Box>
  )
}
