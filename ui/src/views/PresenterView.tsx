import { useCallback, useEffect, useState } from 'react'
import { Deck } from '../deck/Deck'
import { primitiveScenes } from '../pages/primitives'
import { scenes } from '../scenes'

type View = 'presentation' | 'primitives'

interface Route {
  view: View
  /** Zero-based scene index. */
  index: number
}

/*
 * The route lives in the URL hash so a reload keeps your place and it works under
 * file://: "#3" is scene 3 of the presentation, "#primitives/2" is scene 2 of the
 * primitives page. "?primitives" also opens the primitives page.
 */
function readRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const match = /^(primitives)?\/?(\d+)?$/.exec(hash)
  const wantsPrimitives =
    match?.[1] === 'primitives' || new URLSearchParams(window.location.search).has('primitives')
  const view: View = wantsPrimitives || scenes.length === 0 ? 'primitives' : 'presentation'
  const index = Math.max(0, Number(match?.[2] ?? 1) - 1)
  return { view, index }
}

function writeRoute({ view, index }: Route): void {
  const hash = view === 'primitives' ? `#primitives/${index + 1}` : `#${index + 1}`
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

  const onNavigate = useCallback((index: number) => setRoute((r) => ({ ...r, index })), [])
  const togglePrimitives = useCallback(() => {
    if (scenes.length > 0) {
      setRoute((r) => ({ view: r.view === 'primitives' ? 'presentation' : 'primitives', index: 0 }))
    }
  }, [])

  const deck = route.view === 'primitives' ? primitiveScenes : scenes
  return (
    <Deck
      key={route.view}
      scenes={deck}
      index={Math.min(route.index, deck.length - 1)}
      onNavigate={onNavigate}
      onTogglePrimitives={togglePrimitives}
    />
  )
}
