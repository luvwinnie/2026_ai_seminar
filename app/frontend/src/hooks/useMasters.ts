import { useCallback, useEffect, useState } from 'react'
import { fetchMasters } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { MastersByCategory } from '../types'

export interface UseMastersResult {
  data: MastersByCategory | null
  loading: boolean
  error: string | null
  reload: () => void
}

/** 全カテゴリのマスタを取得するフック。reload() で再取得。 */
export function useMasters(): UseMastersResult {
  const [data, setData] = useState<MastersByCategory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    let alive = true
    setLoading(true)
    setError(null)
    fetchMasters()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  // 初回ロード
  useEffect(() => load(), [load])

  const reload = useCallback(() => {
    load()
  }, [load])

  return { data, loading, error, reload }
}
