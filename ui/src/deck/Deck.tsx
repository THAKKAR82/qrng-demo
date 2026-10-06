import { useCallback, useEffect, useState } from 'react'
import { isSynthetic } from '../data/demo'
import { NotesOverlay } from './NotesOverlay'
import { Progress } from './Progress'
import { SyntheticLabel } from './SyntheticLabel'
import type { SceneDef } from './types'
import { useDeckKeys } from './useDeckKeys'
import './Deck.css'

interface DeckProps {
  scenes: readonly SceneDef[]
  index: number
  onNavigate: (index: number) => void
  /** Switch to the other deck (presentation ↔ primitives); omit if there is none. */
  onTogglePrimitives?: () => void
}

function toggleFullscreen(): void {
  const doc = document as Document & { webkitFullscreenElement?: Element | null; webkitExitFullscreen?: () => void }
  const root = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => void }
  try {
    if (document.fullscreenElement ?? doc.webkitFullscreenElement) {
      if (document.exitFullscreen) {
        void document.exitFullscreen().catch(() => undefined)
      } else {
        doc.webkitExitFullscreen?.()
      }
    } else if (root.requestFullscreen) {
      void root.requestFullscreen().catch(() => undefined)
    } else {
      root.webkitRequestFullscreen?.()
    }
  } catch {
    // Fullscreen refused (for example inside a frame): keep presenting in the window.
  }
}

/**
 * Full-screen scenes on a fixed 16:9 stage, with keyboard and clicker navigation,
 * a progress indicator, presenter notes (N), fullscreen (F), and the synthetic-data
 * label whenever the data is synthetic.
 */
export function Deck({ scenes, index, onNavigate, onTogglePrimitives }: DeckProps) {
  const [notesOpen, setNotesOpen] = useState(false)
  const last = scenes.length - 1
  const current = Math.min(Math.max(index, 0), last)
  const scene = scenes[current]

  const go = useCallback(
    (target: number) => onNavigate(Math.min(Math.max(target, 0), last)),
    [onNavigate, last],
  )

  useDeckKeys({
    next: () => go(current + 1),
    previous: () => go(current - 1),
    first: () => go(0),
    last: () => go(last),
    toggleNotes: () => setNotesOpen((open) => !open),
    toggleFullscreen,
    togglePrimitives: () => onTogglePrimitives?.(),
    closeOverlays: () => setNotesOpen(false),
  })

  useEffect(() => {
    document.title = scene === undefined ? 'QRNG demo' : `${scene.title} \u2013 QRNG demo`
  }, [scene])

  if (scene === undefined) {
    return null
  }

  return (
    <div className="stage">
      <main className="stage__frame" aria-roledescription="slide" aria-label={scene.title}>
        {/* The key remounts the scene, so its reveals replay each time it is shown. */}
        <div className="deck__scene" key={scene.id}>
          {scene.render()}
        </div>
        <Progress index={current} count={scenes.length} />
        {notesOpen && <NotesOverlay scene={scene} next={scenes[current + 1]} />}
        {isSynthetic && <SyntheticLabel />}
      </main>
    </div>
  )
}
