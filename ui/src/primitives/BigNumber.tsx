import type { ReactNode } from 'react'
import type { Source } from '../data/types'
import { revealDelay } from '../lib/motion'
import './BigNumber.css'

interface BigNumberProps {
  /** The value, already formatted from demo.json (see lib/format.ts). */
  value: string
  /** Unit set smaller after the value, such as "bits". */
  unit?: string
  /** Which source the number belongs to; sets its colour. Omit for a neutral number. */
  source?: Source
  /** What the number is, in plain words. */
  label: ReactNode
  /** Secondary line, such as the 95% interval. */
  detail?: ReactNode
  /** "hero" (101px) for most numbers, "giant" for the one number that owns a screen. */
  size?: 'hero' | 'giant'
  /** Delay before the number is revealed, in ms. */
  delay?: number
}

/** A headline number in Plex Mono, with its label underneath. */
export function BigNumber({
  value,
  unit,
  source,
  label,
  detail,
  size = 'hero',
  delay = 0,
}: BigNumberProps) {
  const colour = source === undefined ? '' : ` is-${source}`
  return (
    <figure className={`big-number big-number--${size} reveal`} style={revealDelay(delay)}>
      <p className={`big-number__value num${colour}`}>
        {value}
        {unit !== undefined && <span className="big-number__unit">{unit}</span>}
      </p>
      <figcaption className="big-number__label">{label}</figcaption>
      {detail !== undefined && <p className="big-number__detail">{detail}</p>}
    </figure>
  )
}
