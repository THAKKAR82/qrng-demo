import type { ReactNode } from 'react'
import { revealDelay } from '../lib/motion'
import './Scene.css'

interface SceneProps {
  /** The one sentence the audience should take away from this screen. */
  title: ReactNode
  /** Optional supporting sentence under the title. */
  lede?: ReactNode
  /** The scene's content, laid out on the 12-column grid. */
  children?: ReactNode
}

/**
 * One full-screen scene: a left-aligned title block at the top of the 12-column grid,
 * and a body that fills the rest of the stage. Scenes remount when they are shown, so
 * any .reveal inside replays each time.
 */
export function Scene({ title, lede, children }: SceneProps) {
  return (
    <section className="scene">
      <header className="scene__header grid">
        <h1 className="scene__title reveal">{title}</h1>
        {lede !== undefined && (
          <p className="scene__lede reveal" style={revealDelay(80)}>
            {lede}
          </p>
        )}
      </header>
      <div className="scene__body grid">{children}</div>
    </section>
  )
}
