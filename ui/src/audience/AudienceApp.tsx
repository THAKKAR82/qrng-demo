import { useEffect, useState } from 'react'
import { isSynthetic } from '../data/demo'
import { SyntheticLabel } from '../deck/SyntheticLabel'
import { BeatGame } from './BeatGame'
import { ClosingScreen } from './ClosingScreen'
import { IntroScreen } from './IntroScreen'
import type { Screen } from './names'
import { SpotGame } from './SpotGame'
import './audience.css'

const SCREENS: readonly Screen[] = ['intro', 'spot', 'beat', 'end']

/** "#spot", "#beat" and "#end" name a screen; anything else is the intro. */
function readScreen(): Screen {
  const name = window.location.hash.replace(/^#/, '')
  return SCREENS.find((s) => s === name && s !== 'intro') ?? 'intro'
}

/**
 * The phone version (SPEC.md, Section 9.6): an intro, two games, and a closing screen,
 * each an ordinary scrolling page. It has no slides, notes, panels from the talk, or
 * keys, and is not connected to the presenter's app.
 */
export function AudienceApp() {
  const [screen, setScreen] = useState(readScreen)

  useEffect(() => {
    document.title = 'Can you beat a quantum computer?'
    const onHashChange = () => setScreen(readScreen())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // A new hash is a new history entry, so the phone's back button returns to the last screen.
  const go = (next: Screen) => {
    window.location.hash = next === 'intro' ? '' : next
    setScreen(next)
    window.scrollTo({ top: 0 })
  }

  return (
    <div className="phone">
      {isSynthetic && <SyntheticLabel placement="page" />}
      {screen === 'intro' && <IntroScreen go={go} />}
      {screen === 'spot' && <SpotGame go={go} />}
      {screen === 'beat' && <BeatGame go={go} />}
      {screen === 'end' && <ClosingScreen go={go} />}
    </div>
  )
}
