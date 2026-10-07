import { useEffect, useState } from 'react'
import { demo } from '../data/demo'
import type { Running, Source } from '../data/types'
import { usePanelKeys } from '../deck/usePanelKeys'
import { count, percent, percentRange } from '../lib/format'
import { Bitmap } from '../primitives/Bitmap'
import { LineChart } from '../primitives/LineChart'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'
import { MACHINE_NAME } from './machines'
import { ActionButton, MachinePicker, type PanelBaseProps } from './shared'
import './panels.css'

const { cross_checks: checks, copy } = demo

/** Length of each animated phase, in ms. Display pacing only. */
const OBSERVE_MS = 2600
const PREDICT_MS = 3200
/** Bits in one classical output word (SPEC.md, Section 5.1). */
const WORD_BITS = 32

type Phase = 'ready' | 'observing' | 'predicting' | 'done'
type Matchup = 'own' | 'cross'

const MATCHUPS: readonly Segment<Matchup>[] = [
  { value: 'own', label: 'Its own attacker' },
  { value: 'cross', label: 'Swap attackers' },
]

interface Attack {
  /** Plain description of what the attacker does. */
  plan: string
  /** Technical name, for small text. */
  name: string
  trainingBits: number
  accuracy: number
  ciLow: number
  ciHigh: number
  nPredicted: number
  running: Running
  /** The rule-chosen sentence about the result, when there is one. */
  verdict?: string
}

/** What each machine faces: its own attacker, or (cross-check) the other machine's. */
function attackOn(machine: Source, matchup: Matchup): Attack {
  if (matchup === 'own') {
    const a = demo[machine].attacker
    return {
      plan:
        machine === 'classical'
          ? `It watches the first ${count(a.n_training_bits / WORD_BITS)} numbers, rebuilds the generator's hidden state, and then predicts every bit that follows.`
          : `It watches the first half of the shots (${count(a.n_training_bits)} bits), learns which way each qubit leans, and always guesses that.`,
      name: a.name,
      trainingBits: a.n_training_bits,
      accuracy: a.accuracy,
      ciLow: a.ci_low,
      ciHigh: a.ci_high,
      nPredicted: a.n_predicted,
      running: a.running,
      verdict: machine === 'classical' ? copy.classical_attack : copy.quantum_attack,
    }
  }
  const c = machine === 'classical' ? checks.bias_on_classical : checks.mt_on_quantum
  return {
    plan:
      machine === 'classical'
        ? `Cross-check: the quantum machine's attacker (learn each position's lean, then guess it) tried on the classical bits. It watches ${count(c.n_training_bits)} bits first.`
        : `Cross-check: the classical machine's attacker (rebuild the hidden state from ${count(c.n_training_bits / WORD_BITS)} numbers) tried on the quantum bits.`,
    name: c.name,
    trainingBits: c.n_training_bits,
    accuracy: c.accuracy,
    ciLow: c.ci_low,
    ciHigh: c.ci_high,
    nPredicted: c.n_predicted,
    running: c.running,
  }
}

/**
 * The attack's timeline: where it is, from the moment it was launched (null: not yet).
 * Time advances on animation frames while the attack runs; with reduced motion a launch
 * goes straight to the result.
 */
function useTimeline(launchedAt: number | null): { phase: Phase; observed: number; predicted: number } {
  const [now, setNow] = useState(0)
  const total = OBSERVE_MS + PREDICT_MS
  const running = launchedAt !== null && Number.isFinite(launchedAt)
  useEffect(() => {
    if (!running) {
      return
    }
    let frame = 0
    const tick = (time: number) => {
      setNow(time)
      if (launchedAt === null || time - launchedAt < total) {
        frame = requestAnimationFrame(tick)
      }
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [running, launchedAt, total])

  if (launchedAt === null) {
    return { phase: 'ready', observed: 0, predicted: 0 }
  }
  const elapsed = Math.max(0, now - launchedAt)
  if (elapsed < OBSERVE_MS) {
    return { phase: 'observing', observed: elapsed / OBSERVE_MS, predicted: 0 }
  }
  if (elapsed < total) {
    return { phase: 'predicting', observed: 1, predicted: (elapsed - OBSERVE_MS) / PREDICT_MS }
  }
  return { phase: 'done', observed: 1, predicted: 1 }
}

/**
 * Choose a machine and launch the attacker. It first watches the machine's output (the
 * training data, animated), then predicts bits it never saw: its running accuracy replays
 * with the 95% band. "Swap attackers" shows the cross-checks.
 */
export function AttackerPanel({
  placement = 'inline',
  className,
  hideHeader,
  delay,
  keyboard = false,
  chartWidth = 1040,
  chartHeight = 520,
}: PanelBaseProps & { chartWidth?: number; chartHeight?: number }) {
  const [machine, setMachine] = useState<Source>('classical')
  const [matchup, setMatchup] = useState<Matchup>('own')
  const [launchedAt, setLaunchedAt] = useState<number | null>(null)
  const { phase, observed, predicted } = useTimeline(launchedAt)
  const attack = attackOn(machine, matchup)

  const choose = (next: () => void) => {
    next()
    setLaunchedAt(null)
  }
  const launch = () => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // -Infinity puts the timeline at its end at once.
    setLaunchedAt(reduced ? Number.NEGATIVE_INFINITY : performance.now())
  }
  usePanelKeys(
    {
      m: () => choose(() => setMachine(machine === 'classical' ? 'quantum' : 'classical')),
    },
    keyboard,
  )

  const bitmap = demo[machine].bitmap
  const side = bitmap.size
  const showPicture = bitmap.within_training && matchup === 'own'
  const seen = phase === 'ready' ? 0 : phase === 'observing' ? observed : 1
  const pictureFill = Math.round(seen * Math.min(side * side, attack.trainingBits))

  const r = attack.running
  const shown = phase === 'done' ? r.n_bits.length : phase === 'predicting' ? Math.max(1, Math.ceil(predicted * r.n_bits.length)) : 0
  const lastX = r.n_bits[r.n_bits.length - 1]
  const slice = <T,>(xs: readonly T[]) => xs.slice(0, shown)

  return (
    <Panel
      placement={placement}
      className={className}
      hideHeader={hideHeader}
      delay={delay}
      title="Launch the attacker"
      description="An attacker watches a machine's output, then tries to predict bits it has never seen."
      controls={
        <div className="panel-row">
          <MachinePicker value={machine} onChange={(s) => choose(() => setMachine(s))} />
          <SegmentedControl label="Attacker" segments={MATCHUPS} value={matchup} onChange={(m) => choose(() => setMatchup(m))} />
          <ActionButton variant="primary" onClick={launch} disabled={phase === 'observing' || phase === 'predicting'}>
            {phase === 'done' ? 'Launch again' : 'Launch'}
          </ActionButton>
        </div>
      }
    >
      <div className="attacker">
        <div className="attacker__watch">
          <p className="attacker__plan">{attack.plan}</p>
          <p className="term">{attack.name}</p>
          {showPicture && (
            <figure className="attacker__picture">
              <Bitmap
                source={machine}
                bitmap={{ size: side, bits: bitmapBits(bitmap.rows), filled: pictureFill }}
                label={`What the attacker has watched so far from the ${MACHINE_NAME[machine].toLowerCase()}`}
              />
            </figure>
          )}
          <p className="attacker__phase" aria-live="polite">
            {phase === 'ready' && 'Ready. Press Launch.'}
            {phase === 'observing' && (
              <>
                Watching: <Num>{count(Math.round(observed * attack.trainingBits))}</Num> of{' '}
                <Num>{count(attack.trainingBits)}</Num> bits
              </>
            )}
            {phase === 'predicting' && <>Predicting bits it never saw…</>}
            {phase === 'done' && (
              <>
                Watched <Num>{count(attack.trainingBits)}</Num> bits, then predicted <Num>{count(attack.nPredicted)}</Num>.
              </>
            )}
          </p>
        </div>
        <div className="attacker__result">
          {shown > 0 ? (
            <LineChart
              key={`${machine}-${matchup}`}
              title={`Share of bits the attacker guessed right on the ${MACHINE_NAME[machine].toLowerCase()}, as it goes`}
              width={chartWidth}
              height={chartHeight}
              series={[{ id: machine, source: machine, label: 'guessed right', x: slice(r.n_bits), y: slice(r.accuracy) }]}
              bands={[
                {
                  id: `${machine}-band`,
                  source: machine,
                  x: slice(r.n_bits),
                  low: slice(r.ci_low),
                  high: slice(r.ci_high),
                  label: '95% band',
                },
              ]}
              references={[{ y: 0.5, label: 'a coin flip' }]}
              xDomain={[0, lastX]}
              yDomain={[0, 1]}
              yTicks={[0, 0.5, 1]}
              formatY={(v) => percent(v, 0)}
              formatX={(v) => (v === 0 ? '0' : v >= 1000 ? `${count(v / 1000)}k` : count(v))}
              xLabel="bits predicted"
              yLabel="guessed right"
            />
          ) : (
            <div className="attacker__placeholder" />
          )}
          {phase === 'done' && (
            <div className="attacker__final reveal">
              {attack.verdict !== undefined && <p className="attacker__verdict">{attack.verdict}</p>}
              <p>
                Guessed right: <span className={`num is-${machine}`}>{percent(attack.accuracy, 2)}</span>{' '}
                <span className="term">
                  95% interval <Num>{percentRange(attack.ciLow, attack.ciHigh, 2)}</Num>
                </span>
              </p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  )
}

const bitCache = new Map<readonly string[], Uint8Array>()

/** The bitmap's rows as one array of bits, in reading order (cached per bitmap). */
function bitmapBits(rows: readonly string[]): Uint8Array {
  let bits = bitCache.get(rows)
  if (bits === undefined) {
    const joined = rows.join('')
    bits = new Uint8Array(joined.length)
    for (let i = 0; i < joined.length; i += 1) {
      bits[i] = joined.charCodeAt(i) === 49 ? 1 : 0
    }
    bitCache.set(rows, bits)
  }
  return bits
}
