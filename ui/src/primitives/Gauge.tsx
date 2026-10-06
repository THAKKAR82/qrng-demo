import type { CSSProperties, ReactNode } from 'react'
import type { Source } from '../data/types'
import { fixed } from '../lib/format'
import { revealDelay } from '../lib/motion'
import './Gauge.css'

interface GaugeProps {
  /** Min-entropy in bits per bit, 0 to 1. */
  value: number
  /** The conservative bound (lower H∞), drawn as a tick on the bar. */
  conservative?: number
  source: Source
  /** What is being measured, in plain words. */
  label: ReactNode
  /** Secondary line, such as what the tick means. */
  detail?: ReactNode
  /** Draw the 0 to 1 bit scale under this gauge. Stacked gauges show it once, on the last. */
  showScale?: boolean
  delay?: number
}

const clamp = (v: number) => Math.min(1, Math.max(0, v))

/**
 * A bar on a fixed scale from 0 bits (fully predictable) to 1 bit (a coin flip).
 * The scale never moves, so two gauges side by side compare honestly.
 */
export function Gauge({
  value,
  conservative,
  source,
  label,
  detail,
  showScale = false,
  delay = 0,
}: GaugeProps) {
  const v = clamp(value)
  const style = {
    ...revealDelay(delay),
    '--gauge-value': v,
    '--gauge-conservative': conservative === undefined ? 0 : clamp(conservative),
  } as CSSProperties
  return (
    <figure className={`gauge gauge--${source}`} style={style}>
      <figcaption className="gauge__caption reveal" style={revealDelay(delay)}>
        <span className="gauge__label">{label}</span>
        {detail !== undefined && <span className="gauge__detail">{detail}</span>}
      </figcaption>
      <div className="gauge__track">
        <div className="gauge__bar" />
        {conservative !== undefined && <div className="gauge__tick" aria-hidden="true" />}
        <p
          className={`gauge__value num is-${source} reveal${v > 0.5 ? ' gauge__value--end' : ''}`}
          style={revealDelay(delay + 200)}
        >
          {fixed(value, 3)}
          <span className="gauge__unit"> bits</span>
        </p>
      </div>
      {showScale && (
        <div className="gauge__scale" aria-hidden="true">
          <span className="gauge__scale-mark gauge__scale-mark--start">
            <span className="num">0 bits</span>
            <span>fully predictable</span>
          </span>
          <span className="gauge__scale-mark gauge__scale-mark--mid">
            <span className="num">0.5</span>
          </span>
          <span className="gauge__scale-mark gauge__scale-mark--end">
            <span className="num">1 bit</span>
            <span>a coin flip</span>
          </span>
        </div>
      )}
    </figure>
  )
}
