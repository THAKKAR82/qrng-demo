import type { SceneDef } from './types'

interface NotesOverlayProps {
  scene: SceneDef
  /** Current step and step count of the scene. */
  step: number
  steps: number
  next: SceneDef | undefined
}

const KEYS = [
  ['→ PgDn', 'next'],
  ['← PgUp', 'back'],
  ['N', 'notes'],
  ['F', 'fullscreen'],
  ['P', 'primitives'],
  ['Q', 'QR code for phones'],
  ['0 1', 'guess (guess game)'],
  ['R', 'reveal (tell them apart)'],
  ['M', 'switch machine (guess game, attacker)'],
] as const

/** Presenter notes for the current scene, toggled with N and hidden by default. */
export function NotesOverlay({ scene, step, steps, next }: NotesOverlayProps) {
  return (
    <aside className="notes" aria-label="Presenter notes">
      <div>
        <h2 className="notes__heading">
          Notes: {scene.title}
          {steps > 1 && (
            <span className="notes__step num">
              {' '}
              (step {step + 1} of {steps})
            </span>
          )}
        </h2>
        <div className="notes__body">{scene.notes ?? <p className="is-muted">No notes for this scene.</p>}</div>
      </div>
      <div>
        <p className="notes__next">
          {step < steps - 1 ? 'Next: the next step of this scene' : next === undefined ? 'Last scene' : `Next: ${next.title}`}
        </p>
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
