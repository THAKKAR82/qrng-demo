import type { CSSProperties } from 'react'
import type { Source } from '../data/types'
import './BitStream.css'

interface BitStreamProps {
  /** Bits to show, each 0 or 1, in stream order. */
  bits: readonly number[]
  /** The attacker's guess for each bit. When given, each bit shows whether it was guessed. */
  predictions?: readonly number[]
  source: Source
  /** Bits per row; rows wrap. */
  perRow?: number
  /** Accessible name for the whole stream. */
  label: string
  /** Delay before the first bit appears, in ms. */
  delay?: number
  /** Time for the whole stream to appear, in ms; each bit fades in over 200 ms. */
  duration?: number
}

/**
 * A stream of bits in Plex Mono, revealed in order. With predictions, a guessed bit
 * is set in the source colour with a bar beneath it, and a missed bit is set in grey
 * with no bar, so hits and misses differ in shape as well as colour.
 */
export function BitStream({
  bits,
  predictions,
  source,
  perRow = 40,
  label,
  delay = 0,
  duration = 1200,
}: BitStreamProps) {
  const step = bits.length > 1 ? duration / (bits.length - 1) : 0
  return (
    <ol
      className={`bit-stream bit-stream--${source} num`}
      style={{ '--bits-per-row': perRow } as CSSProperties}
      aria-label={label}
    >
      {bits.map((bit, i) => {
        const guessed = predictions === undefined ? undefined : predictions[i] === bit
        const state = guessed === undefined ? '' : guessed ? ' bit--hit' : ' bit--miss'
        return (
          <li
            // Bits never reorder, so the position is a stable key.
            key={i}
            className={`bit${state}`}
            style={{ '--bit-delay': `${Math.round(delay + i * step)}ms` } as CSSProperties}
          >
            {bit}
          </li>
        )
      })}
    </ol>
  )
}
