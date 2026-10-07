import { pools } from '../data/demo'
import type { Source } from '../data/types'
import { readPool } from './pool'

/** Bits shown by the static previews (primitives page): the first of each pool. */
export const PREVIEW_BITS = 200

/** The first PREVIEW_BITS held-out bits of a stream, with the attacker's guesses. */
export function poolPreview(source: Source): { bits: number[]; attacker_predictions: number[] } {
  const { bits, predictions } = readPool(pools[source], 0, Math.min(PREVIEW_BITS, pools[source].length))
  return { bits: Array.from(bits), attacker_predictions: Array.from(predictions) }
}
