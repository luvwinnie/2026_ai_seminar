/**
 * 関連マップ(/analysis/graph) — 報告書どうしの「近さ」の地図。
 * ナレッジベースの Graph View と同じ考え方で、埋め込みの相互kNNで
 * 作ったグラフをバックエンド(GET /api/graph)から受け取り、canvas の
 * 簡易力学レイアウトで描く(依存ライブラリなし・110節なら十分軽い)。
 *
 * - 節の色 = 現象分類 / 大きさ = 損失額(対数)
 * - 強い縁(相互)は濃く、弱い縁は薄く
 * - クリックで報告書詳細へ。ドラッグでつまんで動かせる
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Box, Card, CardContent, Chip, Stack, Typography } from '@mui/material'
import PageHeader from '../components/PageHeader'
import { Loading, ErrorState } from '../components/StateViews'
import { fetchGraph } from '../api/endpoints'
import { errorMessage } from '../api/client'
import type { GraphResponse } from '../types'

const COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#4a3aa7', '#c2417f', '#8a7a12', '#527a8a', '#888888']

interface SimNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  r: number
  color: string
  label: string
  phenomenon: string
}

export default function GraphMap() {
  const navigate = useNavigate()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [data, setData] = useState<GraphResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const hoverRef = useRef<string | null>(null)
  hoverRef.current = hover

  useEffect(() => {
    fetchGraph().then(setData).catch((e) => setError(errorMessage(e)))
  }, [])

  // 現象分類 → 色(凡例と描画で共有)
  const phenColors = useMemo(() => {
    if (!data) return new Map<string, string>()
    const uniq = [...new Set(data.nodes.map((n) => n.phenomenon))]
    return new Map(uniq.map((p, i) => [p, COLORS[i % COLORS.length]]))
  }, [data])

  useEffect(() => {
    if (!data || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')!
    const W = (canvas.width = canvas.clientWidth * devicePixelRatio)
    const H = (canvas.height = canvas.clientHeight * devicePixelRatio)
    ctx.scale(devicePixelRatio, devicePixelRatio)
    const w = W / devicePixelRatio
    const h = H / devicePixelRatio

    const maxCost = Math.max(...data.nodes.map((n) => n.cost), 1)
    const nodes: SimNode[] = data.nodes.map((n, i) => ({
      id: n.id,
      x: w / 2 + Math.cos((i / data.nodes.length) * Math.PI * 2) * Math.min(w, h) * 0.35,
      y: h / 2 + Math.sin((i / data.nodes.length) * Math.PI * 2) * Math.min(w, h) * 0.35,
      vx: 0,
      vy: 0,
      r: 4 + 8 * (Math.log1p(n.cost) / Math.log1p(maxCost)),
      color: phenColors.get(n.phenomenon) ?? '#888',
      label: `${n.id} ${n.part}`,
      phenomenon: n.phenomenon,
    }))
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const links = data.links.map((l) => ({ a: byId.get(l.s)!, b: byId.get(l.t)!, w: l.w, m: l.m }))

    let dragging: SimNode | null = null
    let raf = 0
    let alive = true
    let ticks = 0

    const step = () => {
      // 反発(全対) + 縁のばね + 中心引力(小規模なので O(n^2) で十分)
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          let dx = a.x - b.x
          let dy = a.y - b.y
          const d2 = dx * dx + dy * dy || 1
          const d = Math.sqrt(d2)
          const rep = 900 / d2
          dx /= d
          dy /= d
          a.vx += dx * rep
          a.vy += dy * rep
          b.vx -= dx * rep
          b.vy -= dy * rep
        }
        a.vx += (w / 2 - a.x) * 0.002
        a.vy += (h / 2 - a.y) * 0.002
      }
      for (const l of links) {
        const dx = l.b.x - l.a.x
        const dy = l.b.y - l.a.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const target = l.m ? 70 : 110
        const f = ((d - target) / d) * (l.m ? 0.02 : 0.008)
        l.a.vx += dx * f
        l.a.vy += dy * f
        l.b.vx -= dx * f
        l.b.vy -= dy * f
      }
      for (const n of nodes) {
        if (n === dragging) continue
        n.vx *= 0.85
        n.vy *= 0.85
        n.x = Math.max(12, Math.min(w - 12, n.x + n.vx))
        n.y = Math.max(12, Math.min(h - 12, n.y + n.vy))
      }
    }

    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      for (const l of links) {
        ctx.strokeStyle = l.m ? 'rgba(120,120,140,0.45)' : 'rgba(120,120,140,0.15)'
        ctx.lineWidth = l.m ? 1.4 : 0.7
        ctx.beginPath()
        ctx.moveTo(l.a.x, l.a.y)
        ctx.lineTo(l.b.x, l.b.y)
        ctx.stroke()
      }
      const hv = hoverRef.current
      for (const n of nodes) {
        ctx.beginPath()
        ctx.fillStyle = n.color
        ctx.globalAlpha = hv && hv !== n.id ? 0.45 : 1
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx.fill()
        ctx.globalAlpha = 1
        if (hv === n.id) {
          ctx.strokeStyle = '#0b0b0b'
          ctx.lineWidth = 2
          ctx.stroke()
          ctx.font = '12px sans-serif'
          ctx.fillStyle = '#0b0b0b'
          const pad = 4
          const tw = ctx.measureText(n.label).width
          ctx.fillStyle = 'rgba(255,255,255,0.9)'
          ctx.fillRect(n.x + n.r + 4 - pad, n.y - 14, tw + pad * 2, 18)
          ctx.fillStyle = '#0b0b0b'
          ctx.fillText(n.label, n.x + n.r + 4, n.y)
        }
      }
    }

    const loop = () => {
      if (!alive) return
      if (ticks < 400 || dragging) step()
      ticks++
      draw()
      raf = requestAnimationFrame(loop)
    }
    loop()

    const pick = (ev: MouseEvent): SimNode | null => {
      const rect = canvas.getBoundingClientRect()
      const x = ev.clientX - rect.left
      const y = ev.clientY - rect.top
      let best: SimNode | null = null
      for (const n of nodes) {
        const d = Math.hypot(n.x - x, n.y - y)
        if (d < n.r + 4 && (!best || d < Math.hypot(best.x - x, best.y - y))) best = n
      }
      return best
    }
    const onMove = (ev: MouseEvent) => {
      if (dragging) {
        const rect = canvas.getBoundingClientRect()
        dragging.x = ev.clientX - rect.left
        dragging.y = ev.clientY - rect.top
        return
      }
      const n = pick(ev)
      setHover(n?.id ?? null)
      canvas.style.cursor = n ? 'pointer' : 'default'
    }
    const onDown = (ev: MouseEvent) => {
      dragging = pick(ev)
    }
    const onUp = (ev: MouseEvent) => {
      if (dragging) {
        const moved = Math.hypot(ev.movementX, ev.movementY)
        const n = dragging
        dragging = null
        if (moved < 2) navigate(`/reports/${n.id}`)
      }
    }
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mousedown', onDown)
    canvas.addEventListener('mouseup', onUp)
    return () => {
      alive = false
      cancelAnimationFrame(raf)
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mousedown', onDown)
      canvas.removeEventListener('mouseup', onUp)
    }
  }, [data, phenColors, navigate])

  if (error) return <ErrorState message={error} />
  if (!data) return <Loading />

  return (
    <Box>
      <PageHeader
        title="関連マップ"
        subtitle={`報告書どうしの内容の近さ(${data.mode === 'embedding' ? '埋め込み' : 'キーワード'}相互kNN)。節をクリックで詳細へ`}
      />
      <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: 'wrap', gap: 0.5 }}>
        {[...phenColors.entries()].map(([p, c]) => (
          <Chip key={p} size="small" label={p} sx={{ bgcolor: c, color: '#fff', fontSize: 11 }} />
        ))}
      </Stack>
      <Card variant="outlined">
        <CardContent sx={{ p: 1 }}>
          <canvas ref={canvasRef} style={{ width: '100%', height: '68vh', display: 'block' }} />
          <Typography variant="caption" color="text.secondary" sx={{ px: 1 }}>
            濃い縁=相互に近い(強)、薄い縁=片方向(弱)。大きさ=損失額。検索でもこのグラフの近傍展開を利用しています
          </Typography>
        </CardContent>
      </Card>
    </Box>
  )
}
