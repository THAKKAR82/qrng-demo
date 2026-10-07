import type { ReactNode } from 'react'

/** One screen of the presentation. */
export interface SceneDef {
  /** Stable identifier, unique within its deck. */
  id: string
  /** Short name for the presenter ("next up") and the document title. */
  title: string
  /** Presenter notes, shown with N. Never visible to the audience by default. */
  notes?: ReactNode
  /**
   * Steps within the scene (default 1). "Next" reveals the next step before moving on,
   * and "back" from the first step lands on the previous scene's last step.
   */
  steps?: number
  /** Draws the scene at `step`, from 0 to steps − 1. The scene is not remounted between steps. */
  render: (step: number) => ReactNode
}

/** Number of steps in a scene: at least 1. */
export function stepCount(scene: SceneDef): number {
  return Math.max(1, Math.floor(scene.steps ?? 1))
}
