import type { SceneDef } from './types'

interface NotesOverlayProps {
  scene: SceneDef
  next: SceneDef | undefined
}

const KEYS = [
  ['→ PgDn', 'next'],
  ['← PgUp', 'back'],
  ['N', 'notes'],
  ['F', 'fullscreen'],
  ['P', 'primitives'],
] as const

/** Presenter notes for the current scene, toggled with N and hidden by default. */
export function NotesOverlay({ scene, next }: NotesOverlayProps) {
  return (
    <aside className="notes" aria-label="Presenter notes">
      <div>
        <h2 className="notes__heading">Notes: {scene.title}</h2>
        <div className="notes__body">{scene.notes ?? <p className="is-muted">No notes for this scene.</p>}</div>
      </div>
      <div>
        <p className="notes__next">{next === undefined ? 'Last scene' : `Next: ${next.title}`}</p>
        <dl className="notes__keys">
          {KEYS.map(([key, action]) => (
            <div key={key}>
              <dt className="num">{key}</dt>
              <dd>{action}</dd>
            </div>
          ))}
        </dl>
      </div>
    </aside>
  )
}
