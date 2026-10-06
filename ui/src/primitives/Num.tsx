import type { ReactNode } from 'react'

/** A number inside running text, set in Plex Mono like every other number. */
export function Num({ children }: { children: ReactNode }) {
  return <span className="num">{children}</span>
}
