import type { ChatMessage, ChatSource } from '../types'

interface StreamHandlers {
  onSources?: (sources: ChatSource[]) => void
  onToken?: (text: string) => void
  onDone?: () => void
  onError?: (detail: string) => void
}

/**
 * POST /api/chat/stream を叩き、SSE(text/event-stream)を逐次パースする。
 * イベント: sources / token / done / error(docs/04 §6)。
 */
export async function streamChat(
  message: string,
  history: ChatMessage[],
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history }),
      signal,
    })
  } catch (e) {
    handlers.onError?.(e instanceof Error ? e.message : 'ネットワークエラー')
    return
  }

  if (!res.ok || !res.body) {
    handlers.onError?.(`サーバエラー (HTTP ${res.status})`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (event: string, dataRaw: string) => {
    let data: unknown = {}
    try {
      data = dataRaw ? JSON.parse(dataRaw) : {}
    } catch {
      data = {}
    }
    switch (event) {
      case 'sources':
        handlers.onSources?.((data as { items?: ChatSource[] }).items ?? [])
        break
      case 'token':
        handlers.onToken?.((data as { text?: string }).text ?? '')
        break
      case 'done':
        handlers.onDone?.()
        break
      case 'error':
        handlers.onError?.((data as { detail?: string }).detail ?? 'エラーが発生しました')
        break
    }
  }

  // 1つの SSE ブロック("event:"/"data:" 行の集合)を処理する
  const handleBlock = (block: string) => {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (dataLines.length > 0 || event !== 'message') dispatch(event, dataLines.join('\n'))
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // ブロック区切りは空行(\n\n)
      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        const block = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        if (block.trim()) handleBlock(block)
        sep = buffer.indexOf('\n\n')
      }
    }
    if (buffer.trim()) handleBlock(buffer)
  } catch (e) {
    if ((e as Error)?.name !== 'AbortError') {
      handlers.onError?.(e instanceof Error ? e.message : 'ストリーム読み取りエラー')
    }
  }
}
