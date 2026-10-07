import type { Source } from '../data/types'

/** What the phone games call the two machines, in plain words. */
export const PHONE_NAME: Record<Source, string> = {
  classical: 'Ordinary formula',
  quantum: 'Quantum computer',
}

export const OTHER: Record<Source, Source> = { classical: 'quantum', quantum: 'classical' }

/** The phone version's screens, in order (SPEC.md, Section 9.6). */
export type Screen = 'intro' | 'spot' | 'beat' | 'end'
