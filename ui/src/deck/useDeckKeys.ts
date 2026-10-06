import { useEffect, useRef } from 'react'

export interface DeckKeyActions {
  next: () => void
  previous: () => void
  first: () => void
  last: () => void
  toggleNotes: () => void
  toggleFullscreen: () => void
  /** Switch between the presentation and the primitives page. */
  togglePrimitives: () => void
  closeOverlays: () => void
}

/*
 * Elements that use keys themselves. A key pressed while one of these has focus is
 * left to it, so Space on a button or digits in an input on a future interactive
 * scene never also move the deck.
 */
const INTERACTIVE = [
  'a[href]',
  'button',
  'input',
  'select',
  'textarea',
  'summary',
  'audio[controls]',
  'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
  '[role="button"]',
  '[role="checkbox"]',
  '[role="combobox"]',
  '[role="listbox"]',
  '[role="menuitem"]',
  '[role="option"]',
  '[role="radio"]',
  '[role="slider"]',
  '[role="spinbutton"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="textbox"]',
].join(',')

export function isInteractiveTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(INTERACTIVE) !== null
}

/**
 * Keyboard and presentation-clicker control. Clickers send PageDown and PageUp
 * (some send arrows); all are handled. Keys with a modifier (Cmd-R, Ctrl-F, ...)
 * are left to the browser.
 */
export function useDeckKeys(actions: DeckKeyActions): void {
  // The listener is attached once and always calls the latest actions.
  const latest = useRef(actions)
  useEffect(() => {
    latest.current = actions
  })

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) {
        return
      }
      if (event.isComposing || isInteractiveTarget(event.target)) {
        return
      }
      const a = latest.current
      const handlers: Record<string, (() => void) | undefined> = {
        ArrowRight: a.next,
        ArrowDown: a.next,
        PageDown: a.next,
        ' ': event.shiftKey ? a.previous : a.next,
        ArrowLeft: a.previous,
        ArrowUp: a.previous,
        PageUp: a.previous,
        Home: a.first,
        End: a.last,
        Escape: a.closeOverlays,
      }
      const byLetter: Record<string, (() => void) | undefined> = {
        n: a.toggleNotes,
        f: a.toggleFullscreen,
        p: a.togglePrimitives,
      }
      const handler =
        handlers[event.key] ?? (event.repeat ? undefined : byLetter[event.key.toLowerCase()])
      if (handler !== undefined) {
        event.preventDefault()
        handler()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}
