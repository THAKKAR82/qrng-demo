// The pairs of images for "Spot the quantum machine" (SPEC.md, Section 9.6). Each stream's
// images are shuffled once per page load, and the game reads pairs in that order through
// a session cursor, so no image is shown twice in a session.

import { demo } from '../data/demo'
import type { Source } from '../data/types'
import { unpackBits } from '../lib/pool'

export const SPOT_ROUNDS = 5

export interface SpotImage {
  source: Source
  /** Index into the flattened stream of the image's first bit. */
  startBit: number
  size: number
  bits: Uint8Array
}

export interface SpotPair {
  classical: SpotImage
  quantum: SpotImage
  /** Whether the quantum image goes on the left. */
  quantumLeft: boolean
}

function decode(source: Source): SpotImage[] {
  const { size, images } = demo[source].spot
  return images.map((image) => ({
    source,
    startBit: image.start_bit,
    size,
    bits: unpackBits(image.bits, size * size),
  }))
}

function shuffled<T>(items: readonly T[]): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

const classical = shuffled(decode('classical'))
const quantum = shuffled(decode('quantum'))

/** Pairs available in a session; each is shown at most once. */
export const SPOT_PAIRS = Math.min(classical.length, quantum.length)

const sides = Array.from({ length: SPOT_PAIRS }, () => Math.random() < 0.5)

/** Pair `i` of this session, 0 ≤ i < SPOT_PAIRS. */
export function spotPair(i: number): SpotPair {
  if (!Number.isInteger(i) || i < 0 || i >= SPOT_PAIRS) {
    throw new RangeError(`spot pair ${i} is outside [0, ${SPOT_PAIRS})`)
  }
  return { classical: classical[i], quantum: quantum[i], quantumLeft: sides[i] }
}
