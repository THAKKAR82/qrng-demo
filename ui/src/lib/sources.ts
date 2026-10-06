import type { Source } from '../data/types'

/** The two sources, always in this order: classical first (left), quantum second. */
export const SOURCES: readonly Source[] = ['classical', 'quantum']

/** Display names for the two sources. */
export const SOURCE_NAME: Record<Source, string> = {
  classical: 'Classical',
  quantum: 'Quantum',
}
