// テーマ「CNCコックピット」（05_UI設計書.md §7）。色はここに集め、部品は useTheme() で読む。
import { createTheme, type PaletteMode } from '@mui/material/styles'

interface AppPalette {
  base: string
  paper: string
  elevated: string
  hairline: string
  severity: Record<'critical' | 'high' | 'medium' | 'low', string>
  status: Record<'open' | 'in_progress' | 'completed', string>
}

interface SidebarPalette {
  bg: string
}

declare module '@mui/material/styles' {
  interface Palette {
    app: AppPalette
    sidebar: SidebarPalette
  }
  interface PaletteOptions {
    app?: AppPalette
    sidebar?: SidebarPalette
  }
}

const app: AppPalette = {
  base: '#0E1116',
  paper: '#161B22',
  elevated: '#1D242E',
  hairline: '#2A3340',
  severity: { critical: '#FF5C5C', high: '#FF9F45', medium: '#FFD166', low: '#6EE7A0' },
  status: { open: '#FF9F45', in_progress: '#4CC3E8', completed: '#34D399' },
}

// この版のテーマは夜版（ダーク）の1つだけ
export function createAppTheme(mode: PaletteMode = 'dark') {
  return createTheme({
    palette: {
      mode,
      primary: { main: '#FFA028', light: '#FFB44D' },
      secondary: { main: '#009DC2' },
      error: { main: app.severity.critical },
      warning: { main: app.severity.high },
      info: { main: app.status.in_progress },
      success: { main: app.status.completed },
      background: { default: app.base, paper: app.paper },
      text: { primary: '#E8EDF4', secondary: '#94A3B4', disabled: '#5B6878' },
      divider: app.hairline,
      app,
      sidebar: { bg: '#0A0D11' },
    },
    shape: { borderRadius: 10 },
    components: {
      // カードは影ではなく1px の罫線で区切る
      MuiPaper: {
        styleOverrides: { root: { backgroundImage: 'none' } },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            variants: [
              {
                props: { variant: 'contained', color: 'primary' },
                style: { '&:hover': { backgroundColor: '#FFB44D' } },
              },
            ],
          },
        },
      },
    },
  })
}
