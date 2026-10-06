import { useId } from 'react'
import type { Source } from '../data/types'
import { revealDelay } from '../lib/motion'
import { niceTicks } from '../lib/ticks'
import './LineChart.css'

export interface LineSeries {
  id: string
  source: Source
  /** Direct label drawn at the end of the line. */
  label: string
  x: readonly number[]
  y: readonly number[]
}

/** A shaded range, such as a confidence interval, drawn behind the lines. */
export interface LineBand {
  id: string
  source: Source
  x: readonly number[]
  low: readonly number[]
  high: readonly number[]
  /** Short label for the key above the plot. */
  label?: string
}

/** A dashed horizontal reference, such as "a coin flip, 0.5", labelled below its right end. */
export interface LineReference {
  y: number
  label: string
}

interface LineChartProps {
  /** Accessible summary of what the chart shows. */
  title: string
  series: readonly LineSeries[]
  bands?: readonly LineBand[]
  references?: readonly LineReference[]
  /** Defaults to 0 through the largest x in any series. */
  xDomain?: readonly [number, number]
  yDomain: readonly [number, number]
  xTicks?: readonly number[]
  yTicks: readonly number[]
  xLabel: string
  yLabel: string
  formatX?: (value: number) => string
  formatY?: (value: number) => string
  /** Size on the 1920×1080 stage, in stage pixels. Text inside stays at stage sizes. */
  width?: number
  height?: number
  delay?: number
}

const MARGIN = { top: 56, right: 40, bottom: 104, left: 112 }
const LABEL_GAP = 16
const LABEL_MIN_SEPARATION = 34
const CLIP_BLEED = 6
const KEY_SWATCH = 28

const defaultFormat = (v: number) => v.toLocaleString('en-US')

/**
 * A line chart drawn as SVG in stage pixels: horizontal gridlines only, recessive
 * axes, thick lines in the exact source hues, direct labels instead of a legend box,
 * and optional bands and reference lines. Lines draw in from left to right once.
 */
export function LineChart({
  title,
  series,
  bands = [],
  references = [],
  xDomain,
  yDomain,
  xTicks,
  yTicks,
  xLabel,
  yLabel,
  formatX = defaultFormat,
  formatY = defaultFormat,
  width = 1664,
  height = 560,
  delay = 0,
}: LineChartProps) {
  const clipId = useId()
  const plotW = width - MARGIN.left - MARGIN.right
  const plotH = height - MARGIN.top - MARGIN.bottom
  const [x0, x1] = xDomain ?? [0, Math.max(...series.flatMap((s) => s.x))]
  const [y0, y1] = yDomain
  const sx = (v: number) => MARGIN.left + ((v - x0) / (x1 - x0 || 1)) * plotW
  const sy = (v: number) => MARGIN.top + (1 - (v - y0) / (y1 - y0 || 1)) * plotH
  const path = (xs: readonly number[], ys: readonly number[]) =>
    xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${sx(x).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join('')

  // Direct labels sit just above each line's last point, nudged apart if they collide.
  const ends = series
    .map((s) => {
      const last = s.x.length - 1
      return { s, x: sx(s.x[last]), y: sy(Math.min(y1, Math.max(y0, s.y[last]))) }
    })
    .sort((a, b) => b.y - a.y)
  for (let i = 1; i < ends.length; i += 1) {
    ends[i].y = Math.min(ends[i].y, ends[i - 1].y - LABEL_MIN_SEPARATION)
  }

  const ticksX = xTicks ?? niceTicks(x0, x1)

  return (
    <figure className="line-chart reveal" style={revealDelay(delay)}>
      <svg
        className="line-chart__svg"
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: `calc(${width} * var(--px))` }}
        role="img"
        aria-label={title}
      >
        <defs>
          <clipPath id={clipId}>
            {/* Room for half a line width beyond the plot, so a line at 0% or 100% is not cut. */}
            <rect x={MARGIN.left} y={MARGIN.top - CLIP_BLEED} width={plotW} height={plotH + 2 * CLIP_BLEED} />
          </clipPath>
        </defs>

        <g className="line-chart__grid">
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={MARGIN.left} x2={MARGIN.left + plotW} y1={sy(t)} y2={sy(t)} />
              <text x={MARGIN.left - LABEL_GAP} y={sy(t)} textAnchor="end" dominantBaseline="middle">
                {formatY(t)}
              </text>
            </g>
          ))}
          {ticksX.map((t) => (
            <text key={t} x={sx(t)} y={MARGIN.top + plotH + 36} textAnchor="middle">
              {formatX(t)}
            </text>
          ))}
          <line
            className="line-chart__axis"
            x1={MARGIN.left}
            x2={MARGIN.left + plotW}
            y1={MARGIN.top + plotH}
            y2={MARGIN.top + plotH}
          />
        </g>

        <text className="line-chart__axis-label" x={MARGIN.left - LABEL_GAP} y={MARGIN.top - 28}>
          {yLabel}
        </text>
        <text
          className="line-chart__axis-label"
          x={MARGIN.left + plotW}
          y={height - 12}
          textAnchor="end"
        >
          {xLabel}
        </text>

        <g clipPath={`url(#${clipId})`}>
          {bands.map((b) => (
            <path
              key={b.id}
              className={`line-chart__band line-chart__band--${b.source}`}
              d={`${path(b.x, b.high)}${b.x
                .map((_, i, xs) => {
                  const j = xs.length - 1 - i
                  return `L${sx(xs[j]).toFixed(1)},${sy(b.low[j]).toFixed(1)}`
                })
                .join('')}Z`}
            />
          ))}
          {references.map((r) => (
            <line
              key={r.label}
              className="line-chart__reference"
              x1={MARGIN.left}
              x2={MARGIN.left + plotW}
              y1={sy(r.y)}
              y2={sy(r.y)}
            />
          ))}
          {series.map((s) => (
            <path
              key={s.id}
              className={`line-chart__line line-chart__line--${s.source}`}
              d={path(s.x, s.y)}
              pathLength={1}
            />
          ))}
        </g>

        {references.map((r) => (
          <text
            key={r.label}
            className="line-chart__reference-label"
            x={MARGIN.left + plotW}
            y={sy(r.y) + 32}
            textAnchor="end"
          >
            {r.label}
          </text>
        ))}
        {/* Bands are keyed under the plot, at the left, so they never sit on a line. */}
        {bands
          .filter((b) => b.label !== undefined)
          .map((b, i) => {
            const y = height - 12 - i * LABEL_MIN_SEPARATION
            return (
              <g key={b.id}>
                <rect
                  className={`line-chart__band line-chart__band--${b.source}`}
                  x={MARGIN.left}
                  y={y - 18}
                  width={KEY_SWATCH}
                  height={20}
                />
                <text className={`line-chart__band-label is-${b.source}`} x={MARGIN.left + KEY_SWATCH + 12} y={y}>
                  {b.label}
                </text>
              </g>
            )
          })}
        {ends.map(({ s, x, y }) => (
          <text
            key={s.id}
            className={`line-chart__end-label is-${s.source}`}
            x={x}
            y={y - 24}
            textAnchor="end"
          >
            {s.label}
          </text>
        ))}
      </svg>
    </figure>
  )
}
