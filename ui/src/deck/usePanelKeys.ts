import { useEffect, useRef } from 'react'
import { isInteractiveTarget } from './useDeckKeys'

/**
 * Keys a panel on the current slide answers itself, such as 0 and 1 for a guess or R for a
 * reveal (SPEC.md, Section 9.3). Like the deck's own keys, they are ignored when aimed at
 * an interactive element, with a modifier held, or auto-repeated. Use only keys the deck
 * does not: never arrows, Page keys, Space, Home, End, Escape, N, F, or P.
 *
 * `bindings` maps `KeyboardEvent.key` (lower case for letters) to an action.
 */
export function usePanelKeys(bindings: Record<string, () => void>, enabled = true): void {
  const latest = useRef(bindings)
  useEffect(() => {
    latest.current = bindings
  })

  useEffect(() => {
    if (!enabled) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.repeat) {
        return
      }
      if (event.isComposing || isInteractiveTarget(event.target)) {
        return
      }
      const action = latest.current[event.key.length === 1 ? event.key.toLowerCase() : event.key]
      if (action !== undefined) {
        event.preventDefault()
        action()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled])
}
