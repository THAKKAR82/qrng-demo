// The one place the UI reads demo.json. It is imported at build time, so the built
// page needs no network and no server (SPEC.md, Section 9).

import raw from './demo.json'
import type { DemoData } from './types'

// The assignment is checked by the compiler: if demo.json and types.ts drift apart,
// `npm run typecheck` fails.
export const demo: DemoData = raw

// JSON imports widen literal types, so values the compiler cannot check are checked
// here, once, at load. A failure stops the page rather than showing wrong data.
const isBits = (values: readonly number[]): boolean => values.every((v) => v === 0 || v === 1)
const problems = [
  demo.schema_version === 1 || 'schema_version must be 1',
  ['ibm_quantum_hardware', 'synthetic'].includes(demo.metadata.source) || 'unknown source',
  [demo.quantum, demo.classical].every(
    (s) => isBits(s.next_bits.bits) && isBits(s.next_bits.attacker_predictions),
  ) || 'next_bits must contain only 0 and 1',
].filter((p): p is string => p !== true)
if (problems.length > 0) {
  throw new Error(`demo.json: ${problems.join('; ')}`)
}

/** True if any part of the data is synthetic: the UI must then say so on every screen. */
export const isSynthetic =
  demo.metadata.synthetic || demo.metadata.classical_synthetic || demo.metadata.source !== 'ibm_quantum_hardware'
