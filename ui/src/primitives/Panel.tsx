import type { ReactNode } from 'react'
import { revealDelay } from '../lib/motion'
import './Panel.css'

interface PanelProps {
  /** What the panel lets you do or see, in plain words. */
  title: ReactNode
  /** One supporting sentence. */
  description?: ReactNode
  /** Controls (such as a SegmentedControl), shown above the content. */
  controls?: ReactNode
  children: ReactNode
  /**
   * "inline": inside a Scene on the presenter's stage; the parent places it on the grid.
   * "standalone": a full-width section of the audience view's explore mode.
   */
  placement?: 'inline' | 'standalone'
  /** Extra class, for example to place the panel on the scene grid. */
  className?: string
  delay?: number
}

/**
 * An interactive section of the app. It is marked by a rule across the top, not a box,
 * so a panel inside a scene reads as part of the slide. Controls inside it are at least
 * 44 CSS px and never depend on hover (SPEC.md, Section 9.3).
 */
export function Panel({
  title,
  description,
  controls,
  children,
  placement = 'inline',
  className,
  delay = 0,
}: PanelProps) {
  const classes = ['panel', `panel--${placement}`, 'reveal', className].filter(Boolean).join(' ')
  return (
    <section className={classes} style={revealDelay(delay)}>
      <header className="panel__header">
        <h2 className="panel__title">{title}</h2>
        {description !== undefined && <p className="panel__description">{description}</p>}
      </header>
      {controls !== undefined && <div className="panel__controls">{controls}</div>}
      <div className="panel__content">{children}</div>
    </section>
  )
}
