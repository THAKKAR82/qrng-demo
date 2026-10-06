import type { ReactNode } from 'react'

/** One screen of the presentation. */
export interface SceneDef {
  /** Stable identifier, unique within its deck. */
  id: string
  /** Short name for the presenter ("next up") and the document title. */
  title: string
  /** Presenter notes, shown with N. Never visible to the audience by default. */
  notes?: ReactNode
  render: () => ReactNode
}
