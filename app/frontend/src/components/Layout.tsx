import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link as RouterLink, NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Box,
  Chip,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material'
import { useTheme } from '@mui/material/styles'
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
import SettingsIcon from '@mui/icons-material/SettingsOutlined'
import SummarizeIcon from '@mui/icons-material/SummarizeOutlined'
import AssignmentTurnedInIcon from '@mui/icons-material/AssignmentTurnedInOutlined'
import HubIcon from '@mui/icons-material/HubOutlined'
import DarkModeIcon from '@mui/icons-material/DarkModeOutlined'
import MenuIcon from '@mui/icons-material/Menu'
import AppBar from '@mui/material/AppBar'
import LightModeIcon from '@mui/icons-material/LightModeOutlined'
import type { ReactNode } from 'react'
import { DRAWER_WIDTH } from '../theme'
import { useColorMode } from '../colorMode'
import { fetchHealth } from '../api/endpoints'
import type { HealthResponse } from '../types'
import { Loading } from './StateViews'
import ChatPanel from './ChatPanel'
import SmartToyIcon from '@mui/icons-material/SmartToy'

interface NavItem {
  label: string
  to: string
  icon: ReactNode
}

interface NavSection {
  heading: string
  items: NavItem[]
}

const SECTIONS: NavSection[] = [
  {
    heading: '経営者向け',
    items: [
      { label: 'サマリー', to: '/dashboard', icon: <DashboardIcon /> },
      { label: '予測アラート', to: '/alerts', icon: <NotificationsActiveIcon /> },
      { label: '週次レポート', to: '/digests', icon: <SummarizeIcon /> },
    ],
  },
  {
    heading: '不適合報告書',
    items: [
      { label: '一覧・検索', to: '/reports', icon: <DescriptionIcon /> },
      { label: '新規作成', to: '/reports/new', icon: <AddCircleOutlineIcon /> },
      { label: '是正処置(CAPA)', to: '/capa', icon: <AssignmentTurnedInIcon /> },
    ],
  },
  {
    heading: 'データ分析',
    items: [
      { label: '機械別', to: '/analysis/machines', icon: <PrecisionManufacturingIcon /> },
      { label: '担当者別', to: '/analysis/operators', icon: <PersonIcon /> },
      { label: '顧客別', to: '/analysis/customers', icon: <BusinessIcon /> },
      { label: '時系列', to: '/analysis/trends', icon: <ShowChartIcon /> },
      { label: '関連マップ', to: '/analysis/graph', icon: <HubIcon /> },
      { label: '業務Ontology', to: '/analysis/ontology', icon: <HubIcon /> },
    ],
  },
  {
    heading: '設定',
    items: [{ label: 'マスタ管理', to: '/settings/masters', icon: <SettingsIcon /> }],
  },
]

// チャットバックエンド種別からバッジ表記と警告フラグを決める。
// 旧レスポンス(chat_backend 欠落)では anthropic_configured にフォールバック。
function aiStatus(h: HealthResponse): { label: string; warn: boolean } {
  switch (h.chat_backend) {
    case 'none':
      return { label: 'AI 未設定', warn: true }
    case 'opencode':
      return { label: 'AI: OpenCode', warn: false }
    case 'anthropic':
      return { label: 'AI: Claude', warn: false }
    default:
      return h.anthropic_configured
        ? { label: 'AI 有効', warn: false }
        : { label: 'AI 未設定', warn: true }
  }
}

function HealthBadge() {
  const { palette } = useTheme()
  const sb = palette.sidebar
  const [text, setText] = useState<string | null>(null)
  // AI 未設定 or 未接続をアンバー(注意)で示すためのフラグ
  const [warn, setWarn] = useState(false)

  useEffect(() => {
    let alive = true
    fetchHealth()
      .then((h) => {
        if (!alive) return
        const ai = aiStatus(h)
        setWarn(ai.warn)
        setText(
          `${h.reports}件 · ${h.vector_search === 'e5' ? 'ベクトル検索' : 'キーワード検索'} · ${ai.label}`,
        )
      })
      .catch(() => {
        if (!alive) return
        setWarn(true)
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
        bgcolor: sb.badgeBg,
        color: warn ? sb.accent : sb.textMuted,
        border: `1px solid ${sb.border}`,
        fontSize: 11,
        height: 22,
      }}
    />
  )
}

const CHAT_PANEL_WIDTH = 400

export default function Layout() {
  const location = useLocation()
  const { palette } = useTheme()
  const sb = palette.sidebar
  const { mode, toggle } = useColorMode()

  // AIアシスタント常駐パネル(Drawer風に開閉。閉じてもアンマウントしないので
  // ストリーミング中の回答やWebMCPの画面操作は継続する)
  const [chatOpen, setChatOpen] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem('chatPanelOpen')
      if (stored !== null) return stored !== '0'
    } catch {
      /* localStorage 不可時は画面幅で判断 */
    }
    // 初期値: デスクトップ(lg+)は開く / モバイル・タブレットは閉じる
    return typeof window !== 'undefined' ? window.innerWidth >= 1200 : true
  })
  // モバイル用ナビ(ハンバーガー → 一時Drawer)
  const [navOpen, setNavOpen] = useState(false)

  // チャットパネル幅(ドラッグで可変・記憶。lg+ のインライン表示時のみ)
  const [chatWidth, setChatWidth] = useState<number>(() => {
    try {
      const w = Number(localStorage.getItem('chatPanelWidth'))
      if (w >= 300 && w <= 640) return w
    } catch {
      /* 既定値へ */
    }
    return CHAT_PANEL_WIDTH
  })
  const chatWidthRef = useRef(chatWidth)
  chatWidthRef.current = chatWidth
  const panelRef = useRef<HTMLDivElement>(null)
  const [resizing, setResizing] = useState(false)
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    setResizing(true)
    const onMove = (ev: MouseEvent) => {
      const left = panelRef.current?.getBoundingClientRect().left ?? 0
      setChatWidth(Math.min(640, Math.max(300, ev.clientX - left)))
    }
    const onUp = () => {
      setResizing(false)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try {
        localStorage.setItem('chatPanelWidth', String(chatWidthRef.current))
      } catch {
        /* 保存できなくても動作継続 */
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }
  const resetChatWidth = () => {
    setChatWidth(CHAT_PANEL_WIDTH)
    try {
      localStorage.setItem('chatPanelWidth', String(CHAT_PANEL_WIDTH))
    } catch {
      /* noop */
    }
  }
  const toggleChat = useCallback(() => {
    setChatOpen((o) => {
      try {
        localStorage.setItem('chatPanelOpen', o ? '0' : '1')
      } catch {
        /* localStorage 不可でも動作継続 */
      }
      return !o
    })
  }, [])
  // /chat(全画面チャット)ではパネルを隠して二重表示を避ける
  const isChatRoute = location.pathname === '/chat'
  const panelVisible = chatOpen && !isChatRoute

  const drawerPaperSx = {
    width: DRAWER_WIDTH,
    boxSizing: 'border-box',
    bgcolor: sb.bg,
    color: sb.text,
    borderRight: `1px solid ${sb.border}`,
  }

  const drawerContent = (
    <>
        <Box
          component={RouterLink}
          to="/dashboard"
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
          <InsightsIcon sx={{ color: sb.accent, fontSize: 30 }} />
          <Box>
            <Typography sx={{ fontWeight: 800, fontSize: 18, lineHeight: 1.1, color: sb.text }}>
              DefectReport AI
            </Typography>
            <Typography sx={{ fontSize: 11, color: sb.textMuted }}>製造業 不良報告分析AI</Typography>
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
                    color: sb.textMuted,
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
                // /reports/new は /reports より優先的に判定する
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
                      pl: 1.75,
                      color: sb.textMuted,
                      // 選択時の左アクセントバー(未選択時は透明で幅を確保)
                      borderLeft: '3px solid transparent',
                      '& .MuiListItemIcon-root': { color: sb.textMuted, minWidth: 38 },
                      '&:hover': { bgcolor: sb.hover },
                      '&.Mui-selected, &.active': {
                        bgcolor: sb.tint,
                        borderLeftColor: sb.accent,
                        color: sb.text,
                        '& .MuiListItemIcon-root': { color: sb.accent },
                        '&:hover': { bgcolor: sb.tint },
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

          {/* AI: アシスタントパネルの開閉トグル + 全画面チャット */}
          <List
            subheader={
              <ListSubheader
                disableSticky
                sx={{
                  bgcolor: 'transparent',
                  color: sb.textMuted,
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  lineHeight: '32px',
                  textTransform: 'uppercase',
                }}
              >
                AI
              </ListSubheader>
            }
            sx={{ px: 1.5 }}
          >
            <ListItemButton
              onClick={toggleChat}
              selected={panelVisible}
              aria-label="AIアシスタントパネルを開閉"
              sx={{
                borderRadius: 2,
                mb: 0.5,
                pl: 1.75,
                color: sb.textMuted,
                borderLeft: '3px solid transparent',
                '& .MuiListItemIcon-root': { color: sb.textMuted, minWidth: 38 },
                '&:hover': { bgcolor: sb.hover },
                '&.Mui-selected': {
                  bgcolor: sb.tint,
                  borderLeftColor: sb.accent,
                  color: sb.text,
                  '& .MuiListItemIcon-root': { color: sb.accent },
                  '&:hover': { bgcolor: sb.tint },
                },
              }}
            >
              <ListItemIcon>
                <SmartToyIcon />
              </ListItemIcon>
              <ListItemText
                primary="アシスタント"
                secondary={panelVisible ? '表示中' : '閉じています'}
                slotProps={{
                  primary: { sx: { fontSize: 14, fontWeight: 600 } },
                  secondary: { sx: { fontSize: 10, color: sb.textMuted } },
                }}
              />
            </ListItemButton>
            <ListItemButton
              component={NavLink}
              to="/chat"
              selected={isChatRoute}
              sx={{
                borderRadius: 2,
                mb: 0.5,
                pl: 1.75,
                color: sb.textMuted,
                borderLeft: '3px solid transparent',
                '& .MuiListItemIcon-root': { color: sb.textMuted, minWidth: 38 },
                '&:hover': { bgcolor: sb.hover },
                '&.Mui-selected, &.active': {
                  bgcolor: sb.tint,
                  borderLeftColor: sb.accent,
                  color: sb.text,
                  '& .MuiListItemIcon-root': { color: sb.accent },
                  '&:hover': { bgcolor: sb.tint },
                },
              }}
            >
              <ListItemIcon>
                <ChatIcon />
              </ListItemIcon>
              <ListItemText
                primary="チャット(全画面)"
                slotProps={{ primary: { sx: { fontSize: 14, fontWeight: 600 } } }}
              />
            </ListItemButton>
          </List>
        </Box>

        <Box
          sx={{
            px: 2.5,
            py: 1.5,
            borderTop: `1px solid ${sb.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Typography sx={{ fontSize: 10, color: sb.textMuted }}>セミナー完成イメージ · 2026</Typography>
          <Tooltip title={mode === 'dark' ? 'ライトモードへ' : 'ダークモードへ'}>
            <IconButton
              onClick={toggle}
              size="small"
              aria-label="カラーモード切替"
              sx={{ color: sb.textMuted, '&:hover': { color: sb.accent, bgcolor: sb.hover } }}
            >
              {mode === 'dark' ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Box>
    </>
  )

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      {/* モバイル/タブレット(lg未満)のヘッダーバー */}
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          display: { xs: 'flex', lg: 'none' },
          bgcolor: sb.bg,
          color: sb.text,
          borderBottom: `1px solid ${sb.border}`,
          zIndex: 1202,
        }}
      >
        <Toolbar variant="dense" sx={{ gap: 1 }}>
          <IconButton edge="start" onClick={() => setNavOpen(true)} sx={{ color: sb.text }} aria-label="メニューを開く">
            <MenuIcon />
          </IconButton>
          <InsightsIcon sx={{ color: sb.accent }} />
          <Typography sx={{ fontWeight: 800, fontSize: 16, flex: 1 }}>DefectReport AI</Typography>
          <IconButton onClick={toggleChat} sx={{ color: panelVisible ? sb.accent : sb.text }} aria-label="AIアシスタントを開閉">
            <SmartToyIcon />
          </IconButton>
        </Toolbar>
      </AppBar>

      {/* ナビ: lg+ は常設 / lg未満はハンバーガーからの一時Drawer */}
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', lg: 'block' },
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': drawerPaperSx,
        }}
      >
        {drawerContent}
      </Drawer>
      <Drawer
        variant="temporary"
        open={navOpen}
        onClose={() => setNavOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{ display: { xs: 'block', lg: 'none' }, '& .MuiDrawer-paper': drawerPaperSx }}
      >
        {/* 項目クリックで自動的に閉じる */}
        <Box onClick={() => setNavOpen(false)} sx={{ display: 'contents' }}>
          {drawerContent}
        </Box>
      </Drawer>

      {/* チャットのモバイル用バックドロップ */}
      {panelVisible && (
        <Box
          onClick={toggleChat}
          sx={{
            position: 'fixed',
            inset: 0,
            bgcolor: 'rgba(0,0,0,0.45)',
            zIndex: 1240,
            display: { xs: 'block', lg: 'none' },
          }}
        />
      )}

      {/* AIアシスタント常駐パネル(lg+:インライン列 / lg未満:左からのオーバーレイ)。
          どちらもmountは維持されるため、ストリーミング中の切替でも会話は途切れない */}
      <Box
        ref={panelRef}
        sx={{
          flexShrink: 0,
          overflow: 'hidden',
          bgcolor: 'background.paper',
          borderRight: panelVisible ? '1px solid' : 'none',
          borderColor: 'divider',
          width: { xs: 'min(400px, 88vw)', lg: panelVisible ? chatWidth : 0 },
          position: { xs: 'fixed', lg: 'sticky' },
          top: 0,
          left: 0,
          height: { xs: '100dvh', lg: '100vh' },
          zIndex: { xs: 1250, lg: 'auto' },
          transform: {
            xs: panelVisible ? 'translateX(0)' : 'translateX(-110%)',
            lg: 'none',
          },
          transition: resizing
            ? 'none'
            : 'width 225ms cubic-bezier(0.4,0,0.2,1), transform 225ms cubic-bezier(0.4,0,0.2,1)',
          boxShadow: { xs: panelVisible ? 8 : 0, lg: 0 },
        }}
      >
        <Box sx={{ width: { xs: '100%', lg: chatWidth }, height: '100%' }}>
          <ChatPanel compact onCollapse={toggleChat} />
        </Box>
        {/* リサイズハンドル(lg+のみ。ドラッグで300〜640px、ダブルクリックで既定幅) */}
        {panelVisible && (
          <Box
            onMouseDown={startResize}
            onDoubleClick={resetChatWidth}
            aria-label="チャットパネルの幅を変更"
            sx={{
              position: 'absolute',
              top: 0,
              right: 0,
              width: 6,
              height: '100%',
              cursor: 'col-resize',
              display: { xs: 'none', lg: 'block' },
              zIndex: 2,
              '&:hover': { bgcolor: 'primary.main', opacity: 0.35 },
              ...(resizing ? { bgcolor: 'primary.main', opacity: 0.35 } : {}),
            }}
          />
        )}
      </Box>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, bgcolor: 'background.default' }}>
        {/* lg未満は固定AppBarの高さぶんスペーサー */}
        <Toolbar variant="dense" sx={{ display: { xs: 'block', lg: 'none' } }} />
        <Box sx={{ p: { xs: 1.5, sm: 2, md: 4 }, maxWidth: 1400, mx: 'auto' }}>
          <Suspense fallback={<Loading />}>
            <Outlet />
          </Suspense>
        </Box>
      </Box>
    </Box>
  )
}
