// Scenes of the primitives page (see primitives.tsx), each showing one primitive with
// real data from demo.json.

import { demo } from '../data/demo'
import { PREVIEW_BITS, poolPreview } from '../lib/preview'
import type { CrossCheck } from '../data/types'
import { count, fixed, percent, percentRange } from '../lib/format'
import { revealDelay } from '../lib/motion'
import { SOURCE_NAME, SOURCES } from '../lib/sources'
import { BigNumber } from '../primitives/BigNumber'
import { Bitmap } from '../primitives/Bitmap'
import { BitStream } from '../primitives/BitStream'
import { Gauge } from '../primitives/Gauge'
import { LineChart } from '../primitives/LineChart'
import { Num } from '../primitives/Num'
import { Scene } from '../primitives/Scene'
import { BitmapPanel, NextBitsPanel } from './panels'
import './PrimitiveScenes.css'

const { metadata: meta, quantum, classical } = demo

const stream = { classical, quantum }
const sources = SOURCES

export function RunNotes() {
  return (
    <>
      <p>
        Data from run <span className="num">{meta.run_folder}</span>
        {meta.backend !== null && (
          <>
            {' '}
            on <span className="num">{meta.backend}</span>
          </>
        )}
        {meta.job_id !== null && (
          <>
            , job <span className="num">{meta.job_id}</span>
          </>
        )}
        .
      </p>
      <p>
        <span className="num">
          {count(meta.n_qubits)} × {count(meta.shots)}
        </span>{' '}
        qubits × shots
        {meta.qubits_selected_by_readout_error && meta.qubit_selection_candidates !== null && (
          <>
            , qubits selected by lowest readout error from{' '}
            <span className="num">{count(meta.qubit_selection_candidates)}</span>
          </>
        )}
        .
      </p>
    </>
  )
}

export function CrossCheckNote({ check, stream: on }: { check: CrossCheck; stream: string }) {
  return (
    <p>
      {check.name} on {on} bits: <span className="num">{percent(check.accuracy, 2)}</span> (95%
      interval <span className="num">{percentRange(check.ci_low, check.ci_high, 2)}</span>,{' '}
      {check.consistent_with_half ? 'contains' : 'does not contain'} 50%).
    </p>
  )
}

const TYPE_SCALE = [
  { token: 'giant', px: 180, mono: true },
  { token: 'hero', px: 101, mono: true },
  { token: 'h1', px: 76 },
  { token: 'h2', px: 57 },
  { token: 'h3', px: 43 },
  { token: 'lead', px: 32 },
  { token: 'body', px: 24 },
] as const

// Every non-ASCII character the slides are expected to use, shown in both families.
const GLYPHS = ['H∞', '≈', '×', '±', '→', 'log₂', '0–1', '−0.5', '1 000']

export function TokensScene() {
  return (
    <Scene
      title="Design tokens"
      lede="Plex Sans for words, Plex Mono for numbers and bits, and one colour for each source."
    >
      <div className="tokens__scale">
        {TYPE_SCALE.filter((t) => t.px <= 101).map((t, i) => (
          <div key={t.token} className="tokens__row reveal" style={revealDelay(60 * i)}>
            <span className="tokens__tag num">
              {t.token} {t.px}
            </span>
            <span
              className={`tokens__sample${'mono' in t ? ' num' : ''}`}
              style={{ fontSize: `var(--text-${t.token})` }}
            >
              {'mono' in t ? fixed(quantum.attacker.min_entropy, 3) : 'Can you predict a random bit?'}
            </span>
          </div>
        ))}
      </div>
      <div className="tokens__side">
        <ul className="tokens__colours">
          {sources.map((s, i) => (
            <li key={s} className="tokens__colour reveal" style={revealDelay(300 + 80 * i)}>
              <span className={`tokens__swatch tokens__swatch--${s}`} aria-hidden="true" />
              <span className={`tokens__colour-name is-${s}`}>{SOURCE_NAME[s]}</span>
              <span className="tokens__colour-role">
                The bar is the mark colour, for charts. The name is the text colour.
              </span>
            </li>
          ))}
        </ul>
        <div className="tokens__glyphs reveal" style={revealDelay(480)}>
          {['', 'num'].map((family) => (
            <p key={family} className={`tokens__glyph-row ${family}`}>
              {GLYPHS.map((g) => (
                <span key={g}>{g}</span>
              ))}
            </p>
          ))}
        </div>
      </div>
    </Scene>
  )
}

export function BigNumberScene() {
  return (
    <Scene
      title="BigNumber"
      lede="Min-entropy against each attacker, in bits per bit, with the conservative bound underneath."
    >
      {sources.map((s, i) => {
        const a = stream[s].attacker
        return (
          <div key={s} className={`primitives__half primitives__half--${i}`}>
            <BigNumber
              source={s}
              value={fixed(a.min_entropy, 3)}
              unit="bits"
              label={`${SOURCE_NAME[s]} bits, against the attacker “${a.name}”`}
              detail={
                <>
                  <Num>{fixed(a.min_entropy_conservative, 3)}</Num> bits at the conservative bound
                </>
              }
              delay={150 * i}
            />
          </div>
        )
      })}
    </Scene>
  )
}

export function BitStreamScene() {
  return (
    <Scene
      title="BitStream"
      lede={
        <>
          The first <Num>{count(PREVIEW_BITS)}</Num> bits each attacker never saw. A bar marks
          every bit the attacker guessed right; misses are grey.
        </>
      }
    >
      {sources.map((s, i) => {
        const next = poolPreview(s)
        return (
          <div key={s} className={`primitives__half primitives__half--${i} primitives__stack`}>
            <p className={`primitives__caption is-${s}`}>{SOURCE_NAME[s]}</p>
            <BitStream
              source={s}
              bits={next.bits}
              predictions={next.attacker_predictions}
              perRow={25}
              label={`${SOURCE_NAME[s]}: the next ${next.bits.length} bits and the attacker's guesses`}
              delay={200 + 300 * i}
            />
          </div>
        )
      })}
    </Scene>
  )
}

export function BitmapScene() {
  const side = quantum.bitmap.size
  return (
    <Scene
      title="Bitmap"
      lede={
        <>
          The first <Num>{count(side * side)}</Num> bits of each stream, one square per bit: 1 is coloured, 0 is
          blank.
        </>
      }
    >
      {sources.map((s, i) => (
        <figure key={s} className={`primitives__bitmap primitives__bitmap--${i}`}>
          <Bitmap
            source={s}
            bitmap={stream[s].bitmap}
            label={`${SOURCE_NAME[s]} bits as a ${side} by ${side} picture`}
            delay={150 * i}
          />
          <figcaption className={`primitives__caption is-${s}`}>{SOURCE_NAME[s]}</figcaption>
        </figure>
      ))}
    </Scene>
  )
}

export function GaugeScene() {
  return (
    <Scene
      title="Gauge"
      lede="Min-entropy on a fixed scale from 0 to 1 bit. The bar is the point estimate; the tick is the conservative bound."
    >
      <div className="primitives__gauges">
        {sources.map((s, i) => {
          const a = stream[s].attacker
          return (
            <Gauge
              key={s}
              source={s}
              value={a.min_entropy}
              conservative={a.min_entropy_conservative}
              label={`${SOURCE_NAME[s]}, against “${a.name}”`}
              detail={
                <>
                  conservative bound <Num>{fixed(a.min_entropy_conservative, 3)}</Num> bits
                </>
              }
              showScale={i === sources.length - 1}
              delay={200 * i}
            />
          )
        })}
      </div>
    </Scene>
  )
}

export function LineChartScene() {
  const q = quantum.attacker
  const last = (xs: readonly number[]) => xs[xs.length - 1]
  return (
    <Scene
      title="LineChart"
      lede="Each attacker's running accuracy on bits it never saw. The band is the 95% interval of the final accuracy."
    >
      <div className="primitives__chart-wide">
        <LineChart
          title="Running accuracy of both attackers, from 0 to 100 percent"
          width={960}
          height={540}
          series={sources.map((s) => ({
            id: s,
            source: s,
            label: SOURCE_NAME[s],
            x: stream[s].attacker.running.n_bits,
            y: stream[s].attacker.running.accuracy,
          }))}
          references={[{ y: 0.5, label: 'a coin flip, 50%' }]}
          yDomain={[0, 1]}
          yTicks={[0, 0.25, 0.5, 0.75, 1]}
          formatY={(v) => percent(v, 0)}
          xTicks={[0, 50_000, 100_000, 150_000]}
          formatX={(v) => (v === 0 ? '0' : `${v / 1000}k`)}
          xLabel="bits predicted"
          yLabel="guessed right"
        />
      </div>
      <div className="primitives__chart-narrow">
        <LineChart
          title="Running accuracy of the quantum attacker, zoomed to 44 to 56 percent, with the 95 percent interval of its final accuracy"
          width={672}
          height={540}
          series={[
            { id: 'quantum', source: 'quantum', label: 'Quantum', x: q.running.n_bits, y: q.running.accuracy },
          ]}
          bands={[
            {
              id: 'quantum-ci',
              source: 'quantum',
              x: [0, last(q.running.n_bits)],
              low: [q.ci_low, q.ci_low],
              high: [q.ci_high, q.ci_high],
              label: `95% interval ${percentRange(q.ci_low, q.ci_high)}`,
            },
          ]}
          references={[{ y: 0.5, label: 'a coin flip' }]}
          yDomain={[0.44, 0.56]}
          yTicks={[0.44, 0.47, 0.5, 0.53, 0.56]}
          formatY={(v) => percent(v, 0)}
          xTicks={[0, 50_000, 100_000]}
          formatX={(v) => (v === 0 ? '0' : `${v / 1000}k`)}
          xLabel="bits predicted"
          yLabel="guessed right, zoomed"
          delay={200}
        />
      </div>
    </Scene>
  )
}

export function PanelScene() {
  return (
    <Scene
      title="Panel"
      lede="Interactive sections of a slide. Controls are at least 44 CSS px and work by tap, click, or keyboard."
    >
      <BitmapPanel className="primitives__panel-left" />
      <NextBitsPanel className="primitives__panel-right" perRow={36} delay={150} />
    </Scene>
  )
}
