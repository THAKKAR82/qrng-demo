// The held-out bit pools from demo.json (SCHEMA.md, `pool`), and the only ways the UI reads
// them. Pool bits are never repeated or wrapped: every read is bounded, and asking for a
// bit past the end throws instead of starting over.
//
// This file is also run directly by Node (from tests/test_ui_stats.py), so it imports
// nothing and uses only erasable TypeScript syntax.

/** A pool as stored in demo.json: bits packed 8 per byte, most significant bit first, base64. */
export interface PackedPool {
  start_bit: number
  n_bits: number
  bits: string
  predictions: string
}

export interface BitPool {
  /** Index into the flattened stream of the first pool bit. */
  readonly startBit: number
  readonly length: number
  /** One entry per pool bit, 0 or 1. */
  readonly bits: Uint8Array
  /** The attacker's guess for each pool bit, 0 or 1. */
  readonly predictions: Uint8Array
}

/** Rounds the guessing game must be able to play from any starting offset. */
export const GUESS_ROUNDS = 200

/** Unpack `n` bits from base64 of bytes, most significant bit first (NumPy `packbits`). */
export function unpackBits(base64: string, n: number): Uint8Array {
  const bytes = atob(base64)
  if (bytes.length !== Math.ceil(n / 8)) {
    throw new Error(`packed bits hold ${bytes.length} bytes, expected ${Math.ceil(n / 8)}`)
  }
  const bits = new Uint8Array(n)
  for (let i = 0; i < n; i += 1) {
    bits[i] = (bytes.charCodeAt(i >> 3) >> (7 - (i & 7))) & 1
  }
  return bits
}

export function decodePool(packed: PackedPool): BitPool {
  if (!Number.isInteger(packed.n_bits) || packed.n_bits <= 0) {
    throw new Error(`pool size must be a positive integer, got ${packed.n_bits}`)
  }
  return {
    startBit: packed.start_bit,
    length: packed.n_bits,
    bits: unpackBits(packed.bits, packed.n_bits),
    predictions: unpackBits(packed.predictions, packed.n_bits),
  }
}

/** Pool bits `[from, from + count)` and the attacker's guesses for them. Never wraps. */
export function readPool(
  pool: BitPool,
  from: number,
  count: number,
): { bits: Uint8Array; predictions: Uint8Array } {
  if (!Number.isInteger(from) || !Number.isInteger(count) || from < 0 || count < 0 || from + count > pool.length) {
    throw new RangeError(`pool read [${from}, ${from + count}) is outside [0, ${pool.length})`)
  }
  return {
    bits: pool.bits.subarray(from, from + count),
    predictions: pool.predictions.subarray(from, from + count),
  }
}

/**
 * How far a stream at `position` may advance when it asks for `wanted` more bits: never
 * past the end of the pool. Zero means the pool is used up and the stream must stop.
 */
export function advanceBy(position: number, wanted: number, length: number): number {
  return Math.max(0, Math.min(wanted, length - position))
}

/**
 * A random starting offset for the guessing game, in [0, length − rounds], so at least
 * `rounds` rounds fit before the end of the pool. `random` returns a number in [0, 1).
 */
export function randomStart(length: number, rounds: number = GUESS_ROUNDS, random: () => number = Math.random): number {
  if (length < rounds) {
    throw new RangeError(`a pool of ${length} bits cannot hold ${rounds} rounds`)
  }
  const span = length - rounds + 1
  return Math.min(span - 1, Math.floor(random() * span))
}
