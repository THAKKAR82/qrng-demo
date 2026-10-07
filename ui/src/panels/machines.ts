import type { Source } from '../data/types'

/** Plain names for the two machines, used by every panel and slide. */
export const MACHINE_NAME: Record<Source, string> = {
  classical: 'Classical machine',
  quantum: 'Quantum machine',
}
