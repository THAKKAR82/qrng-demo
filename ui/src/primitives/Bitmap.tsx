import { useEffect, useRef } from 'react'
import type { Bitmap as BitmapData, Source } from '../data/types'
import { revealDelay } from '../lib/motion'
import './Bitmap.css'

interface BitmapProps {
  bitmap: BitmapData
  source: Source
  /** Accessible description of what the picture shows. */
  label: string
  delay?: number
}

/**
 * A square picture of bits, one cell per bit: 1 in the source colour, 0 as the
 * background, matching bitmap_cmap in pipeline/plotstyle.py. It is drawn on a canvas
 * at the device's real resolution with cell edges rounded to whole device pixels, so
 * every cell is crisp and equal at any window size.
 */
export function Bitmap({ bitmap, source, label, delay = 0 }: BitmapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas === null) {
      return
    }
    const draw = () => {
      const styles = getComputedStyle(canvas)
      const on = styles.getPropertyValue(`--color-${source}-mark`).trim()
      const off = styles.getPropertyValue('--color-surface').trim()
      const side = Math.max(1, Math.round(canvas.clientWidth * window.devicePixelRatio))
      canvas.width = side
      canvas.height = side
      const context = canvas.getContext('2d')
      if (context === null) {
        return
      }
      const n = bitmap.size
      const edge = (i: number) => Math.round((i * side) / n)
      context.fillStyle = off
      context.fillRect(0, 0, side, side)
      context.fillStyle = on
      bitmap.rows.forEach((row, r) => {
        const y = edge(r)
        const h = edge(r + 1) - y
        for (let c = 0; c < n; c += 1) {
          if (row.charCodeAt(c) === 49) {
            const x = edge(c)
            context.fillRect(x, y, edge(c + 1) - x, h)
          }
        }
      })
    }
    draw()
    const observer = new ResizeObserver(draw)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [bitmap, source])

  return (
    <canvas
      ref={canvasRef}
      className={`bitmap bitmap--${source} reveal`}
      style={revealDelay(delay)}
      role="img"
      aria-label={label}
    />
  )
}
