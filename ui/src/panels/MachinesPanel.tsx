import { useEffect, useRef, useState, type ReactNode } from 'react'
import { pools } from '../data/demo'
import type { Source } from '../data/types'
import { count, fixed, percent } from '../lib/format'
import { useLiveRun } from '../lib/live'
import { advanceBy, pictureShape, type PictureShape } from '../lib/pool'
import { useSessionNumber } from '../lib/session'
import { SOURCES } from '../lib/sources'
import { bitStats, countOnes } from '../lib/stats'
import { Bitmap } from '../primitives/Bitmap'
import { BitStream } from '../primitives/BitStream'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'
import { LiveRunButton, LiveRunFacts, LiveRunStatus } from './LiveRun'
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

/** Side of the picture of recorded bits, in cells; it shows the first side² bits generated. */
const PICTURE_SIDE = 128
/** Most recent bits written out as digits. */
const RECENT_BITS = 16

/**
 * Classical and quantum side by side. "Generate bits" streams held-out bits from each
 * pool; the pictures fill in and the counts update as bits arrive. It stops for good at
 * the end of the recorded bits, and a slide shown again carries on where it stopped.
 *
 * Served by an armed live server (SPEC.md, Section 6.4), it also offers one small live
 * run. Its fresh bits then play on the quantum machine, from the start and in step with
 * the classical machine, until they run out.
 */
export function MachinesPanel({ placement = 'inline', className, hideHeader, delay }: PanelBaseProps) {
  const live = useLiveRun()
  const fresh = __QRNG_LIVE__ ? live.result : null
  const quantumBits = fresh !== null ? fresh.bits : pools.quantum.bits
  // Both streams play in step, so the shorter one sets the end.
  const length = Math.min(pools.classical.length, quantumBits.length)
  // A live run's pictures are sized to its bits (40 × 50 for 2,000), not 128 × 128.
  const shape = fresh !== null ? pictureShape(length) : null

  const [position, setPosition] = useSessionNumber(
    fresh !== null ? `machines:live:${fresh.runId}` : 'machines:position',
    () => 0,
  )
  const [wantsToPlay, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<Speed>('medium')
  // Fresh bits start playing as soon as they arrive.
  const [shownRun, setShownRun] = useState<string | null>(null)
  if (fresh !== null && fresh.runId !== shownRun) {
    setShownRun(fresh.runId)
    setPlaying(true)
  }
  const ended = position >= length
  const playing = wantsToPlay && !ended

  // Advance on animation frames while playing, never past the end of the pools.
  const carry = useRef(0)
  const latest = useRef({ position, speed, length })
  useEffect(() => {
    latest.current = { position, speed, length }
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
        const step = advanceBy(latest.current.position, wanted, latest.current.length)
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
      {__QRNG_LIVE__ && <LiveRunButton live={live} />}
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
          <Machine
            key={source}
            source={source}
            bits={source === 'quantum' ? quantumBits : pools.classical.bits}
            position={position}
            shape={shape}
            facts={
              source === 'classical' ? (
                <ClassicalRunFacts />
              ) : __QRNG_LIVE__ && fresh !== null ? (
                <LiveRunFacts result={fresh} />
              ) : (
                <QuantumRunFacts />
              )
            }
          />
        ))}
      </div>
      <p className="machines__status" aria-live="polite">
        {ended ? (
          <>{fresh !== null ? 'End of the fresh bits.' : 'End of the recorded bits.'}</>
        ) : (
          <>
            <Num>{count(position)}</Num> of <Num>{count(length)}</Num>{' '}
            {fresh !== null ? 'bits from each machine (fresh quantum bits)' : 'recorded bits from each machine'}
          </>
        )}
      </p>
      {__QRNG_LIVE__ && <LiveRunStatus live={live} />}
    </Panel>
  )
}

interface MachineProps {
  source: Source
  /** The stream being played: a pool, or a live run's fresh bits. */
  bits: Uint8Array
  position: number
  /** The picture's shape for a live run; null for the 128 × 128 picture of recorded bits. */
  shape: PictureShape | null
  facts: ReactNode
}

function Machine({ source, bits: stream, position, shape, facts }: MachineProps) {
  // Bounded like readPool: bits are never repeated or wrapped (SPEC.md, Section 9.5).
  if (!Number.isInteger(position) || position < 0 || position > stream.length) {
    throw new RangeError(`read of ${position} bits from a stream of ${stream.length}`)
  }
  const bits = stream.subarray(0, position)
  const ones = countOnes(bits)
  const { fractionOnes, entropy } = bitStats(ones, position)
  const recent = Array.from(bits.subarray(Math.max(0, position - RECENT_BITS)))
  return (
    <section className={`machine machine--${source}`} aria-label={MACHINE_NAME[source]}>
      <h3 className={`machine__name is-${source}`}>{MACHINE_NAME[source]}</h3>
      <div className="machine__body">
        <div className="machine__picture">
          <div className="machine__frame">
            <Bitmap
              source={source}
              bitmap={
                shape === null
                  ? { size: PICTURE_SIDE, bits: stream, filled: position }
                  : { size: shape.columns, rows: shape.rows, bits: stream, filled: position }
              }
              label={`${MACHINE_NAME[source]}: the ${count(Math.min(position, shape === null ? PICTURE_SIDE ** 2 : shape.columns * shape.rows))} bits generated so far as a picture${shape === null ? '' : `, ${shape.columns} wide and ${shape.rows} tall`}`}
            />
          </div>
          {shape !== null && (
            <p className="term machine__caption">
              <Num>{count(shape.columns)}</Num> × <Num>{count(shape.rows)}</Num> bits
            </p>
          )}
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
      {facts}
    </section>
  )
}
