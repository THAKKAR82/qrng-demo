import type { CSSProperties } from 'react'

/**
 * Inline style for a .reveal element that should start `ms` after the scene appears.
 * Stagger results so they arrive in reading order; reduced motion makes them instant.
 */
export function revealDelay(ms: number): CSSProperties {
  return { '--reveal-delay': `${Math.round(ms)}ms` } as CSSProperties
}
