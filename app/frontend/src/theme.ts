import { createTheme } from '@mui/material/styles'
import type { Theme } from '@mui/material/styles'

// ============================================================
// テーマ「CNCコックピット」— 艶消しグラファイトの面にスパークアンバーが灯る計器盤。
// ライト(昼版)/ダーク(夜版)の両モードを createAppTheme(mode) で生成する。
// 色は MUI palette に集約し、各コンポーネントは useTheme() 経由で参照する。
// チャート系列は dataviz バリデータ(各モードのサーフェス)で検証済み。
// ============================================================

export type AppMode = 'light' | 'dark'

export const DRAWER_WIDTH = 264
// 計器の読み出し風・等幅フォント(KPI 数値など)。モード非依存。
export const MONO_FONT = "'SF Mono', ui-monospace, 'Cascadia Mono', Consolas, monospace"

// --- カスタムパレット型 ---
export interface AppSurfaces {
  base: string // アプリ基調
  paper: string // カード
  elevated: string // 入力・ホバー・ヘッダセル
  hairline: string // 1px 罫線(境界)
}

export interface SidebarPalette {
  bg: string
  hover: string
  tint: string // 選択項目の薄い下地
  border: string
  text: string
  textMuted: string
  accent: string // 選択アクセント(アンバー)
  badgeBg: string
}

export interface ChartPalette {
  series: string[] // categorical(固定順)
  grid: string
  axis: string
  danger: string // UCL/LCL・管理外れ点
  neutral: string // p̄・抑制ライン
  amber: string
  cyan: string
  violet: string
  green: string
  rose: string
  severity: Record<string, string>
  status: Record<string, string>
}

// MUI palette にカスタムキーを追加(module augmentation)
declare module '@mui/material/styles' {
  interface Palette {
    app: AppSurfaces
    sidebar: SidebarPalette
    chart: ChartPalette
  }
  interface PaletteOptions {
    app: AppSurfaces
    sidebar: SidebarPalette
    chart: ChartPalette
  }
}

// サイドバーは両モードとも暗色トーン(=共通アイデンティティ「操作盤」)
const SIDEBAR_LIGHT: SidebarPalette = {
  bg: '#141922',
  hover: 'rgba(255,255,255,0.06)',
  tint: 'rgba(255,160,40,0.12)',
  border: '#232A35',
  text: '#E8EDF4',
  textMuted: '#94A3B4',
  accent: '#FFA028',
  badgeBg: 'rgba(255,255,255,0.06)',
}

const SIDEBAR_DARK: SidebarPalette = {
  bg: '#0A0D11',
  hover: 'rgba(255,255,255,0.06)',
  tint: 'rgba(255,160,40,0.10)',
  border: '#2A3340',
  text: '#E8EDF4',
  textMuted: '#94A3B4',
  accent: '#FFA028',
  badgeBg: 'rgba(255,255,255,0.06)',
}

// --- ダーク(夜版)---
const DARK = {
  app: { base: '#0E1116', paper: '#161B22', elevated: '#1D242E', hairline: '#2A3340' } as AppSurfaces,
  amber: '#FFA028',
  amberHover: '#FFB44D',
  amberContrast: '#1A1206',
  cyan: '#009DC2',
  text: { primary: '#E8EDF4', secondary: '#94A3B4', disabled: '#5B6878' },
  chart: {
    // dataviz 検証済み(dark, surface #161B22): 明度をずらし彩度を抑えた5系列
    series: ['#C88300', '#009DC2', '#7A66B8', '#239168', '#A64F7C'],
    grid: '#1F2630', // 基調+数% の控えめなグリッド(#2A3340 はボーダー用)
    axis: '#94A3B4',
    danger: '#FF5C5C',
    neutral: '#94A3B4',
    amber: '#C88300',
    cyan: '#009DC2',
    violet: '#7A66B8',
    green: '#239168',
    rose: '#A64F7C',
    severity: { critical: '#FF5C5C', high: '#FF9F45', medium: '#FFD166', low: '#6EE7A0' },
    status: { open: '#FF9F45', in_progress: '#4CC3E8', completed: '#34D399' },
  } as ChartPalette,
  sidebar: SIDEBAR_DARK,
}

// --- ライト(昼版)---
const LIGHT = {
  app: { base: '#F5F6F8', paper: '#FFFFFF', elevated: '#EDEFF2', hairline: '#DCE0E6' } as AppSurfaces,
  amber: '#E58A17', // 白背景での視認性のためやや濃く
  amberHover: '#C97710',
  amberContrast: '#1A1206',
  cyan: '#0089AD',
  text: { primary: '#1A222E', secondary: '#5B6878', disabled: '#9AA6B4' },
  chart: {
    // dataviz 検証済み(light, surface #FFFFFF): 同色相でやや濃く
    series: ['#BD7900', '#0089AD', '#6E55B1', '#008B5E', '#A44477'],
    grid: '#E6E9EE',
    axis: '#5B6878',
    danger: '#DC2626',
    neutral: '#5B6878',
    amber: '#BD7900',
    cyan: '#0089AD',
    violet: '#6E55B1',
    green: '#008B5E',
    rose: '#A44477',
    // 白背景の小さなチップ文字でも AA(4.5:1)を満たすよう十分濃く
    severity: { critical: '#BE1B24', high: '#9A3412', medium: '#854D0E', low: '#166534' },
    status: { open: '#9A3412', in_progress: '#0369A1', completed: '#166534' },
  } as ChartPalette,
  sidebar: SIDEBAR_LIGHT,
}

/** モードに応じた MUI テーマを生成する */
export function createAppTheme(mode: AppMode): Theme {
  const t = mode === 'dark' ? DARK : LIGHT
  return createTheme({
    palette: {
      mode,
      primary: { main: t.amber, light: t.amberHover, contrastText: t.amberContrast },
      secondary: { main: t.cyan, contrastText: mode === 'dark' ? '#04151B' : '#FFFFFF' },
      background: { default: t.app.base, paper: t.app.paper },
      text: t.text,
      divider: t.app.hairline,
      error: { main: t.chart.severity.critical },
      warning: { main: t.chart.severity.high },
      info: { main: t.chart.status.in_progress },
      success: { main: t.chart.status.completed },
      app: t.app,
      sidebar: t.sidebar,
      chart: t.chart,
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
      MuiCssBaseline: {
        styleOverrides: { body: { backgroundColor: t.app.base } },
      },
      MuiCard: {
        defaultProps: { elevation: 0 },
        styleOverrides: {
          // カードは影ではなくヘアライン境界で仕上げる
          root: {
            backgroundColor: t.app.paper,
            border: `1px solid ${t.app.hairline}`,
            backgroundImage: 'none',
            boxShadow: 'none',
          },
        },
      },
      MuiPaper: {
        styleOverrides: { root: { backgroundImage: 'none' } },
      },
      MuiTableCell: {
        styleOverrides: {
          head: { fontWeight: 700, backgroundColor: t.app.elevated, color: t.text.secondary },
          root: { borderColor: t.app.hairline },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: { root: { backgroundColor: t.app.elevated } },
      },
      MuiButtonBase: {
        styleOverrides: {
          // ホバー等の微アニメーションは控えめに(150ms)
          root: { transition: 'background-color 150ms ease, border-color 150ms ease, color 150ms ease' },
        },
      },
    },
  })
}
