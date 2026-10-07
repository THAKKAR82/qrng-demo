// The one place the UI reads demo.json. It is imported at build time, so the built
// page needs no network and no server (SPEC.md, Section 9).

import { decodePool, type BitPool } from '../lib/pool'
import raw from './demo.json'
import type { DemoData, Source } from './types'

// The assignment is checked by the compiler: if demo.json and types.ts drift apart,
// `npm run typecheck` fails.
export const demo: DemoData = raw

// JSON imports widen literal types, so values the compiler cannot check are checked
// here, once, at load. A failure stops the page rather than showing wrong data.
const isPair = (v: readonly number[]) => v.length === 2 && v.every(Number.isInteger)
const layout = demo.layout
const problems = [
  demo.schema_version === 3 || 'schema_version must be 3',
  ['ibm_quantum_hardware', 'synthetic'].includes(demo.metadata.source) || 'unknown source',
  [demo.quantum, demo.classical].every((s) => s.pool.start_bit >= s.attacker.n_training_bits) ||
    'a pool starts inside the training data',
  layout === null ||
    (layout.coordinates.length === layout.num_qubits &&
      layout.coordinates.every(isPair) &&
      layout.edges.every((e) => isPair(e) && e.every((q) => q >= 0 && q < layout.num_qubits))) ||
    'layout coordinates or edges are malformed',
].filter((p): p is string => p !== true)
if (problems.length > 0) {
  throw new Error(`demo.json: ${problems.join('; ')}`)
}

/** Each stream's held-out pool, decoded once (decodePool checks the packed lengths). */
export const pools: Record<Source, BitPool> = {
  classical: decodePool(demo.classical.pool),
  quantum: decodePool(demo.quantum.pool),
}

/** True if any part of the data is synthetic: the UI must then say so on every screen. */
export const isSynthetic =
  demo.metadata.synthetic || demo.metadata.classical_synthetic || demo.metadata.source !== 'ibm_quantum_hardware'
