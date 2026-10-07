import type { SceneDef } from '../deck/types'
import { talkScenes } from './talk'

/** The presentation's scenes, in order (SPEC.md, Section 9.4). */
export const scenes: readonly SceneDef[] = talkScenes
