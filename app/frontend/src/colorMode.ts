import { createContext, useContext } from 'react'
import type { AppMode } from './theme'

// カラーモード(ライト/ダーク)の状態と操作。
// Provider 本体は ColorModeContext.tsx(コンポーネント)に置き、
// ここはコンポーネント以外(コンテキスト・フック)のみを公開する。

export interface ColorModeContextValue {
  mode: AppMode
  toggle: () => void
  setMode: (mode: AppMode) => void
}

export const ColorModeContext = createContext<ColorModeContextValue | undefined>(undefined)

export const THEME_STORAGE_KEY = 'theme-mode'

/** 初期モード: localStorage の保存値 → OS の prefers-color-scheme → dark */
export function initialColorMode(): AppMode {
  if (typeof window === 'undefined') return 'dark'
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

/** モードの読み取り・切替 */
export function useColorMode(): ColorModeContextValue {
  const ctx = useContext(ColorModeContext)
  if (!ctx) throw new Error('useColorMode must be used within AppThemeProvider')
  return ctx
}
