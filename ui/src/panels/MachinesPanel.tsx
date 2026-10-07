import { useEffect, useRef, useState } from 'react'
import { pools } from '../data/demo'
import type { Source } from '../data/types'
import { count, fixed, percent } from '../lib/format'
import { advanceBy, readPool } from '../lib/pool'
import { useSessionNumber } from '../lib/session'
import { SOURCES } from '../lib/sources'
import { bitStats, countOnes } from '../lib/stats'
import { Bitmap } from '../primitives/Bitmap'
import { BitStream } from '../primitives/BitStream'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'
import { MACHINE_NAME } from './machines'
import { ActionButton, ClassicalRunFacts, QuantumRunFacts, type PanelBaseProps } from './shared'
import './panels.css'

type Speed = 'slow' | 'medium' | 'fast'

/** Bits per second at each speed. Display pacing only. */
const BITS_PER_SECOND: Record<Speed, number> = { slow: 12, medium: 400, fast: 4000 }

const SPEEDS: readonly Segment<Speed>[] = [
  { value: 'slow', label: 'Slow' },
  { value: 'medium', label: 'Medium' },
  { value: 'fast', label: 'Fast' },
]

/** Side of the live picture, in cells; it shows the first side² bits generated. */
const PICTURE_SIDE = 128
/** Most recent bits written out as digits. */
const RECENT_BITS = 16

/** Both streams play in step, so the shorter pool sets the end. */
const LENGTH = Math.min(pools.classical.length, pools.quantum.length)

/**
 * Classical and quantum side by side. "Generate bits" streams held-out bits from each
 * pool; the pictures fill in and the counts update as bits arrive. It stops for good at
 * the end of the recorded bits, and a slide shown again carries on where it stopped.
 */
export function MachinesPanel({ placement = 'inline', className,
  hideHeader, delay }: PanelBaseProps) {
  const [position, setPosition] = useSessionNumber('machines:position', () => 0)
  const [wantsToPlay, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<Speed>('medium')
  const ended = position >= LENGTH
  const playing = wantsToPlay && !ended

  // Advance on animation frames while playing, never past the end of the pools.
  const carry = useRef(0)
  const latest = useRef({ position, speed })
  useEffect(() => {
    latest.current = { position, speed }
  })
  useEffect(() => {
    if (!playing) {
      return
    }
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      carry.current += ((now - last) / 1000) * BITS_PER_SECOND[latest.current.speed]
      last = now
      const wanted = Math.floor(carry.current)
      if (wanted > 0) {
        carry.current -= wanted
        const step = advanceBy(latest.current.position, wanted, LENGTH)
        if (step === 0) {
          return
        }
        setPosition(latest.current.position + step)
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, setPosition])

  const controls = (
    <div className="panel-row">
      <ActionButton variant="primary" onClick={() => setPlaying((p) => !p)} disabled={ended}>
        {playing ? 'Pause' : position === 0 ? 'Generate bits' : 'Keep generating'}
      </ActionButton>
      <SegmentedControl label="Speed" segments={SPEEDS} value={speed} onChange={setSpeed} />
    </div>
  )

  return (
    <Panel
      placement={placement}
      className={className}
      hideHeader={hideHeader}
      delay={delay}
      title="Two machines making random bits"
      description="Each square is one bit: coloured for 1, blank for 0. Both machines play back bits they really made."
      controls={controls}
    >
      <div className="machines">
        {SOURCES.map((source) => (
          <Machine key={source} source={source} position={position} />
        ))}
      </div>
      <p className="machines__status" aria-live="polite">
        {ended ? (
          <>End of the recorded bits.</>
        ) : (
          <>
            <Num>{count(position)}</Num> of <Num>{count(LENGTH)}</Num> recorded bits from each machine
          </>
        )}
      </p>
    </Panel>
  )
}

function Machine({ source, position }: { source: Source; position: number }) {
  const pool = pools[source]
  const { bits } = readPool(pool, 0, position)
  const ones = countOnes(bits)
  const { fractionOnes, entropy } = bitStats(ones, position)
  const recent = Array.from(bits.subarray(Math.max(0, position - RECENT_BITS)))
  return (
    <section className={`machine machine--${source}`} aria-label={MACHINE_NAME[source]}>
      <h3 className={`machine__name is-${source}`}>{MACHINE_NAME[source]}</h3>
      <div className="machine__body">
        <div className="machine__picture">
          <Bitmap
            source={source}
            bitmap={{ size: PICTURE_SIDE, bits: pool.bits, filled: position }}
            label={`${MACHINE_NAME[source]}: the ${count(Math.min(position, PICTURE_SIDE ** 2))} bits generated so far as a picture`}
          />
        </div>
        <dl className="machine__stats">
          <div>
            <dt>Share of 1s</dt>
            <dd className={`num is-${source}`}>{position === 0 ? '–' : percent(fractionOnes, 1)}</dd>
          </div>
          <div>
            <dt>
              Ordinary randomness score <span className="term">Shannon entropy, bits per bit (1 = perfectly balanced)</span>
            </dt>
            <dd className={`num is-${source}`}>{position === 0 ? '–' : fixed(entropy, 4)}</dd>
          </div>
          <div>
            <dt>Latest bits</dt>
            <dd className="machine__recent">
              {recent.length === 0 ? (
                <span className="num is-muted">–</span>
              ) : (
                <BitStream
                  source={source}
                  bits={recent}
                  perRow={RECENT_BITS}
                  duration={0}
                  label={`${MACHINE_NAME[source]}: the latest ${recent.length} bits`}
                />
              )}
            </dd>
          </div>
        </dl>
      </div>
      {source === 'quantum' ? <QuantumRunFacts /> : <ClassicalRunFacts />}
    </section>
  )
}
