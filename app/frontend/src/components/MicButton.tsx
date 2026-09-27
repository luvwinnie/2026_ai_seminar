/**
 * 音声入力ボタン(docs/10 B-6) — Web Speech API(ja-JP)。非対応ブラウザでは表示しない。
 */
import { useEffect, useRef, useState } from 'react'
import { IconButton, Tooltip } from '@mui/material'
import MicIcon from '@mui/icons-material/Mic'
import MicOffIcon from '@mui/icons-material/MicOff'

type SpeechRecognitionLike = {
  lang: string
  interimResults: boolean
  continuous: boolean
  start: () => void
  stop: () => void
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
}

function getRecognizer(): SpeechRecognitionLike | null {
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike
    webkitSpeechRecognition?: new () => SpeechRecognitionLike
  }
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition
  return Ctor ? new Ctor() : null
}

export default function MicButton({ onText, disabled }: { onText: (t: string) => void; disabled?: boolean }) {
  const [supported, setSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const recRef = useRef<SpeechRecognitionLike | null>(null)

  useEffect(() => {
    setSupported(getRecognizer() !== null)
  }, [])

  const toggle = () => {
    if (listening) {
      recRef.current?.stop()
      return
    }
    const rec = getRecognizer()
    if (!rec) return
    rec.lang = 'ja-JP'
    rec.interimResults = false
    rec.continuous = false
    rec.onresult = (ev) => {
      const t = Array.from({ length: ev.results.length }, (_, i) => ev.results[i][0].transcript).join('')
      if (t) onText(t)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recRef.current = rec
    setListening(true)
    rec.start()
  }

  if (!supported) return null
  return (
    <Tooltip title={listening ? '音声入力を停止' : '音声で入力(日本語)'}>
      <span>
        <IconButton size="small" color={listening ? 'error' : 'default'} onClick={toggle} disabled={disabled} aria-label="音声入力">
          {listening ? <MicOffIcon fontSize="small" /> : <MicIcon fontSize="small" />}
        </IconButton>
      </span>
    </Tooltip>
  )
}
