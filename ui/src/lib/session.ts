import { useCallback, useSyncExternalStore } from 'react'

// Numbers that last for one page load and are shared by every component that reads them,
// such as how far the live streams have read into a pool. A slide that is shown again, or
// the same panel on another slide, carries on from where it was instead of starting over,
// so pool bits are never shown twice as if they were new (SPEC.md, Section 9.5).

const values = new Map<string, number>()
const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function read(key: string, initial: () => number): number {
  let value = values.get(key)
  if (value === undefined) {
    value = initial()
    values.set(key, value)
  }
  return value
}

/** A session-wide number, created by `initial` the first time `key` is read. */
export function useSessionNumber(key: string, initial: () => number): [number, (next: number) => void] {
  const value = useSyncExternalStore(subscribe, () => read(key, initial))
  const set = useCallback(
    (next: number) => {
      values.set(key, next)
      listeners.forEach((l) => l())
    },
    [key],
  )
  return [value, set]
}
