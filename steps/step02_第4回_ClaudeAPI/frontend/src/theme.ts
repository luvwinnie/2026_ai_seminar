import { createTheme } from '@mui/material/styles'

// サイドバーは濃紺 (#0f172a / #1e293b)、メイン領域は明るい背景。
// セミナー向けに視認性の高いカラーパレットを定義する。
export const SIDEBAR_BG = '#0f172a'
export const SIDEBAR_ACCENT = '#1e293b'
export const SIDEBAR_SELECTED = '#2563eb'
export const DRAWER_WIDTH = 264

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#2563eb' },
    secondary: { main: '#f59e0b' },
    background: { default: '#f1f5f9', paper: '#ffffff' },
    error: { main: '#dc2626' },
    warning: { main: '#f59e0b' },
    info: { main: '#0ea5e9' },
    success: { main: '#16a34a' },
  },
  typography: {
    fontFamily:
      '"Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", "Noto Sans JP", Meiryo, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(15,23,42,0.06)' },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        head: { fontWeight: 700, backgroundColor: '#f8fafc' },
      },
    },
  },
})

// Recharts 用の共通カラーパレット
export const CHART_COLORS = [
  '#2563eb',
  '#f59e0b',
  '#16a34a',
  '#dc2626',
  '#8b5cf6',
  '#0ea5e9',
  '#ec4899',
  '#14b8a6',
  '#f97316',
  '#64748b',
]

export const SEVERITY_CHART_COLORS: Record<string, string> = {
  critical: '#dc2626',
  high: '#f59e0b',
  medium: '#0ea5e9',
  low: '#16a34a',
}

export default theme
