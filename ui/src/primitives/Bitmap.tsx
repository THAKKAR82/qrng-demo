import { useEffect, useRef } from 'react'
import type { Bitmap as BitmapData, Source } from '../data/types'
import { revealDelay } from '../lib/motion'
import './Bitmap.css'

/** Bits filling in live, in reading order: cell i shows bits[i] once i < filled. */
export interface LiveBits {
  /** Cells per row. */
  size: number
  /** Rows, when the picture is not square (a live run's bits); defaults to `size`. */
  rows?: number
  bits: ArrayLike<number>
  /** Cells drawn so far; the rest stay blank. */
  filled: number
}

interface BitmapProps {
  bitmap: BitmapData | LiveBits
  source: Source
  /**
   * "source" draws 1 in the source colour; "neutral" draws it in ink, so two pictures
   * can be compared without the colour giving their source away.
   */
  tone?: 'source' | 'neutral'
  /** Accessible description of what the picture shows. */
  label: string
  delay?: number
}

function isLive(bitmap: BitmapData | LiveBits): bitmap is LiveBits {
  return 'filled' in bitmap
}

/** Columns and rows of the picture: square unless live bits say otherwise. */
function shapeOf(bitmap: BitmapData | LiveBits): { columns: number; rows: number } {
  return { columns: bitmap.size, rows: isLive(bitmap) ? (bitmap.rows ?? bitmap.size) : bitmap.size }
}

/**
 * A square picture of bits, one cell per bit: 1 in the source colour, 0 as the
 * background, matching bitmap_cmap in pipeline/plotstyle.py. It is drawn on a canvas
 * at the device's real resolution with cell edges rounded to whole device pixels, so
 * every cell is crisp and equal at any window size. Given live bits, it draws the cells
 * filled so far and redraws as more arrive.
 */
export function Bitmap({ bitmap, source, tone = 'source', label, delay = 0 }: BitmapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const drawRef = useRef<() => void>(() => undefined)

  // Redraw whenever the picture or its colour changes (after every render; cheap), and
  // keep the latest drawing function for the resize observer below.
  useEffect(() => {
    drawRef.current = () => draw(canvasRef.current, bitmap, source, tone)
    drawRef.current()
  })

  // Redraw whenever the canvas changes size.
  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas === null) {
      return
    }
    const observer = new ResizeObserver(() => drawRef.current())
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [])

  // A picture that isn't square keeps square cells and fits inside the same square as a
  // square picture: as tall as it when portrait, as wide as it when landscape.
  const { columns, rows } = shapeOf(bitmap)
  const shape =
    columns === rows
      ? {}
      : { aspectRatio: `${columns} / ${rows}`, width: `${(100 * Math.min(1, columns / rows)).toFixed(4)}%` }
  return (
    <canvas
      ref={canvasRef}
      className={`bitmap bitmap--${tone === 'neutral' ? 'neutral' : source}${columns === rows ? '' : ' bitmap--shaped'} reveal`}
      style={{ ...revealDelay(delay), ...shape }}
      role="img"
      aria-label={label}
    />
  )
}

function draw(
  canvas: HTMLCanvasElement | null,
  bitmap: BitmapData | LiveBits,
  source: Source,
  tone: 'source' | 'neutral',
): void {
  if (canvas === null) {
    return
  }
  const styles = getComputedStyle(canvas)
  const on = styles.getPropertyValue(tone === 'neutral' ? '--color-ink' : `--color-${source}-mark`).trim()
  const off = styles.getPropertyValue('--color-surface').trim()
  const { columns, rows } = shapeOf(bitmap)
  const width = Math.max(1, Math.round(canvas.clientWidth * window.devicePixelRatio))
  const height = Math.max(1, Math.round(canvas.clientHeight * window.devicePixelRatio))
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width
    canvas.height = height
  }
  const context = canvas.getContext('2d')
  if (context === null) {
    return
  }
  const n = bitmap.size
  const edgeX = (i: number) => Math.round((i * width) / columns)
  const edgeY = (i: number) => Math.round((i * height) / rows)
  const cell = (r: number, c: number) => {
    const x = edgeX(c)
    const y = edgeY(r)
    context.fillRect(x, y, edgeX(c + 1) - x, edgeY(r + 1) - y)
  }
  context.fillStyle = off
  context.fillRect(0, 0, width, height)
  context.fillStyle = on
  if (isLive(bitmap)) {
    const filled = Math.min(bitmap.filled, columns * rows, bitmap.bits.length)
    for (let i = 0; i < filled; i += 1) {
      if (bitmap.bits[i] === 1) {
        cell(Math.floor(i / columns), i % columns)
      }
    }
  } else {
    bitmap.rows.forEach((row, r) => {
      for (let c = 0; c < n; c += 1) {
        if (row.charCodeAt(c) === 49) {
          cell(r, c)
        }
      }
    })
  }
}
