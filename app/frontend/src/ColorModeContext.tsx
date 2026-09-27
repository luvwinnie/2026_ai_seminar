import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import { createAppTheme } from './theme'
import type { AppMode } from './theme'
import {
  ColorModeContext,
  THEME_STORAGE_KEY,
  initialColorMode,
  type ColorModeContextValue,
} from './colorMode'

/** ライト/ダークのモード管理 + MUI テーマ供給をまとめたプロバイダ */
export function AppThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<AppMode>(initialColorMode)

  const setMode = useCallback((next: AppMode) => {
    setModeState(next)
    window.localStorage.setItem(THEME_STORAGE_KEY, next)
  }, [])

  const toggle = useCallback(() => {
    setModeState((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark'
      window.localStorage.setItem(THEME_STORAGE_KEY, next)
      return next
    })
  }, [])

  // モード切替時のみテーマを再生成
  const theme = useMemo(() => createAppTheme(mode), [mode])

  // ルート要素にモード属性を付与(将来のCSS拡張・デバッグ用)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode)
    document.documentElement.style.colorScheme = mode
  }, [mode])

  const ctx = useMemo<ColorModeContextValue>(() => ({ mode, toggle, setMode }), [mode, toggle, setMode])

  return (
    <ColorModeContext.Provider value={ctx}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ColorModeContext.Provider>
  )
}
