import { useCallback, useEffect, useState } from 'react'
import { Deck } from '../deck/Deck'
import { primitiveScenes } from '../pages/primitives'
import { scenes } from '../scenes'

type View = 'presentation' | 'primitives'

interface Route {
  view: View
  /** Zero-based scene index. */
  index: number
  /** Zero-based step within the scene. */
  step: number
}

/*
 * The route lives in the URL hash so a reload keeps your place and it works under
 * file://: "#3" is scene 3 of the presentation, "#4.2" is step 2 of scene 4, and
 * "#primitives/2" is scene 2 of the primitives page. "?primitives" also opens the
 * primitives page. With no hash the presentation opens on its first scene.
 */
function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const match = /^(primitives)?\/?(?:(\d+)(?:\.(\d+))?)?$/.exec(hash)
  const wantsPrimitives =
    match?.[1] === 'primitives' || new URLSearchParams(window.location.search).has('primitives')
  const view: View = wantsPrimitives || scenes.length === 0 ? 'primitives' : 'presentation'
  const index = Math.max(0, Number(match?.[2] ?? 1) - 1)
  const step = Math.max(0, Number(match?.[3] ?? 1) - 1)
  return { view, index, step }
}

function writeRoute({ view, index, step }: Route): void {
  const scene = step > 0 ? `${index + 1}.${step + 1}` : `${index + 1}`
  const hash = view === 'primitives' ? `#primitives/${scene}` : `#${scene}`
  if (window.location.hash !== hash) {
    window.history.replaceState(null, '', hash)
  }
}

/** The presenter's view: the slide deck on the projector. */
export function PresenterView() {
  const [route, setRoute] = useState(readRoute)

  useEffect(() => {
    const onHashChange = () => setRoute(readRoute())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => writeRoute(route), [route])

  const onNavigate = useCallback(
    (index: number, step: number) => setRoute((r) => ({ ...r, index, step })),
    [],
  )
  const togglePrimitives = useCallback(() => {
    if (scenes.length > 0) {
      setRoute((r) => ({ view: r.view === 'primitives' ? 'presentation' : 'primitives', index: 0, step: 0 }))
    }
  }, [])

  const deck = route.view === 'primitives' ? primitiveScenes : scenes
  return (
    <Deck
      key={route.view}
      scenes={deck}
      index={Math.min(route.index, deck.length - 1)}
      step={route.step}
      onNavigate={onNavigate}
      onTogglePrimitives={togglePrimitives}
    />
  )
}
