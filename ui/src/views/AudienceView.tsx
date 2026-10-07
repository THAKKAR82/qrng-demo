import { useEffect, useState, type ReactNode } from 'react'
import { demo, isSynthetic } from '../data/demo'
import { SyntheticLabel } from '../deck/SyntheticLabel'
import { count, utcDate } from '../lib/format'
import { AttackerPanel } from '../panels/AttackerPanel'
import { GuessGamePanel } from '../panels/GuessGamePanel'
import { HardwarePanel } from '../panels/HardwarePanel'
import { MachinesPanel } from '../panels/MachinesPanel'
import { ActionButton } from '../panels/shared'
import { TellApartPanel } from '../panels/TellApartPanel'
import { UnpredictabilityPanel } from '../panels/UnpredictabilityPanel'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'
import './AudienceView.css'

const { metadata: meta } = demo

/** Where the data came from, in one or two plain lines. Every value is from demo.json. */
function RunLine() {
  const hardware = meta.source === 'ibm_quantum_hardware' && !isSynthetic
  return (
    <div className="audience__run">
      <p>
        {hardware && meta.backend !== null ? (
          <>
            Measured on IBM Quantum <span className="num">{meta.backend}</span>
          </>
        ) : (
          <>
            Sample data <span className="num">{meta.run_folder}</span>
          </>
        )}
        {meta.date_utc !== null && <>, {utcDate(meta.date_utc)}</>}
      </p>
      <p className="is-muted">
        <span className="num">{count(meta.n_qubits)}</span> qubits, <span className="num">{count(meta.shots)}</span> shots
        {meta.qubits_selected_by_readout_error && meta.qubit_selection_candidates !== null && (
          <>
            ; qubits picked for lowest readout error from{' '}
            <span className="num">{count(meta.qubit_selection_candidates)}</span>
          </>
        )}
      </p>
    </div>
  )
}

interface Stop {
  id: string
  /** Heading for this stop of the tour, matching the talk. */
  title: string
  intro: string
  render: () => ReactNode
}

/** The tour, in the same order as the talk (SPEC.md, Section 9.1). */
const STOPS: readonly Stop[] = [
  {
    id: 'machines',
    title: 'Meet the two machines',
    intro: 'One is an ordinary computer program; the other measured qubits on a real quantum computer. Press Generate bits.',
    render: () => <MachinesPanel placement="standalone" />,
  },
  {
    id: 'tell-apart',
    title: 'Can you tell them apart?',
    intro: 'Guess which picture came from which machine, then reveal.',
    render: () => <TellApartPanel placement="standalone" gaugesOnReveal />,
  },
  {
    id: 'guess',
    title: 'Guess the next bit',
    intro: 'Tap 0 or 1 to guess each bit before it is shown.',
    render: () => <GuessGamePanel placement="standalone" />,
  },
  {
    id: 'attacker',
    title: 'Enter the attacker',
    intro: 'Now play alongside an attacker that has studied each machine, then launch it yourself.',
    render: () => (
      <>
        <GuessGamePanel placement="standalone" showAttacker />
        <AttackerPanel placement="standalone" chartWidth={600} chartHeight={520} />
      </>
    ),
  },
  {
    id: 'unpredictability',
    title: 'Measuring unpredictability',
    intro: 'One number for each machine: how surprising its bits are to someone trying to predict them.',
    render: () => <UnpredictabilityPanel placement="standalone" />,
  },
  {
    id: 'hardware',
    title: 'The chip behind the bits',
    intro: 'The quantum computer’s qubits. Tap one to see how it behaved.',
    render: () => <HardwarePanel placement="standalone" />,
  },
]

type Mode = 'tour' | 'explore'

const MODES: readonly Segment<Mode>[] = [
  { value: 'tour', label: 'Guided tour' },
  { value: 'explore', label: 'Explore all' },
]

/** "#tour/3" is stop 3 of the tour; "#explore" is everything on one page. */
function readRoute(): { mode: Mode; stop: number } {
  const match = /^#(tour|explore)(?:\/(\d+))?$/.exec(window.location.hash)
  const mode: Mode = match?.[1] === 'explore' ? 'explore' : 'tour'
  const stop = Math.min(Math.max(Number(match?.[2] ?? 1) - 1, 0), STOPS.length - 1)
  return { mode, stop }
}

/**
 * The audience's phone view: a short guided tour through the panels in the same order as
 * the talk, or every panel on one page. It runs from a static hosted copy and is not
 * connected to the presenter's app; participation in the talk is in person (SPEC.md,
 * Section 9.1).
 */
export function AudienceView() {
  const [route, setRoute] = useState(readRoute)

  useEffect(() => {
    document.title = 'Can you predict a random bit?'
    const onHashChange = () => setRoute(readRoute())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    const hash = route.mode === 'explore' ? '#explore' : `#tour/${route.stop + 1}`
    if (window.location.hash !== hash) {
      window.history.replaceState(null, '', hash)
    }
  }, [route])

  const goTo = (stop: number) => {
    setRoute({ mode: 'tour', stop })
    window.scrollTo({ top: 0 })
  }

  const stop = STOPS[route.stop]
  return (
    <div className="audience">
      {isSynthetic && <SyntheticLabel placement="page" />}
      <header className="audience__header">
        <h1 className="audience__title">Can you predict a random bit?</h1>
        <RunLine />
        <SegmentedControl label="Mode" segments={MODES} value={route.mode} onChange={(mode) => setRoute((r) => ({ ...r, mode }))} />
      </header>
      {route.mode === 'tour' ? (
        <main className="audience__tour" key={stop.id}>
          <p className="audience__step is-muted">
            Step <span className="num">{route.stop + 1}</span> of <span className="num">{STOPS.length}</span>
          </p>
          <h2 className="audience__stop">{stop.title}</h2>
          <p className="audience__intro">{stop.intro}</p>
          <div className="audience__panels">{stop.render()}</div>
          <nav className="audience__nav" aria-label="Tour">
            <ActionButton onClick={() => goTo(route.stop - 1)} disabled={route.stop === 0}>
              Back
            </ActionButton>
            {route.stop < STOPS.length - 1 ? (
              <ActionButton variant="primary" onClick={() => goTo(route.stop + 1)}>
                Next: {STOPS[route.stop + 1].title}
              </ActionButton>
            ) : (
              <ActionButton variant="primary" onClick={() => setRoute((r) => ({ ...r, mode: 'explore' }))}>
                Explore everything
              </ActionButton>
            )}
          </nav>
        </main>
      ) : (
        <main className="audience__panels">
          {STOPS.map((s) => (
            <section key={s.id} className="audience__section" aria-label={s.title}>
              {s.render()}
            </section>
          ))}
        </main>
      )}
    </div>
  )
}
