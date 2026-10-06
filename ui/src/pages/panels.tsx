// Interactive panels built from the primitives, with real data from demo.json. Each one
// works inside a presenter scene ("inline") and in the audience view's explore mode
// ("standalone"). They describe the data; they make no comparative claims (SPEC.md,
// Section 4.3).

import { useState } from 'react'
import { demo } from '../data/demo'
import type { Source } from '../data/types'
import { count, fixed, percent, percentRange } from '../lib/format'
import { SOURCE_NAME, SOURCES } from '../lib/sources'
import { Bitmap } from '../primitives/Bitmap'
import { BitStream } from '../primitives/BitStream'
import { Gauge } from '../primitives/Gauge'
import { LineChart } from '../primitives/LineChart'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'
import './panels.css'

const { quantum, classical } = demo
const stream = { classical, quantum }

const SOURCE_SEGMENTS: readonly Segment<Source>[] = [
  { value: 'classical', label: SOURCE_NAME.classical, source: 'classical' },
  { value: 'quantum', label: SOURCE_NAME.quantum, source: 'quantum' },
]

type Placement = 'inline' | 'standalone'

interface PanelPlacement {
  placement?: Placement
  className?: string
  delay?: number
}

function SourcePicker({ value, onChange }: { value: Source; onChange: (s: Source) => void }) {
  return <SegmentedControl label="Stream" segments={SOURCE_SEGMENTS} value={value} onChange={onChange} />
}

/** The first bits of one stream as a picture; pick the stream. */
export function BitmapPanel({ placement = 'inline', className, delay }: PanelPlacement) {
  const [source, setSource] = useState<Source>('quantum')
  const side = stream[source].bitmap.size
  return (
    <Panel
      placement={placement}
      className={className}
      delay={delay}
      title="Random bits as a picture"
      description={
        <>
          The first <Num>{count(side * side)}</Num> bits, one square per bit: 1 is coloured, 0 is blank.
        </>
      }
      controls={<SourcePicker value={source} onChange={setSource} />}
    >
      <div className="panel-bitmap">
        <Bitmap
          key={source}
          source={source}
          bitmap={stream[source].bitmap}
          label={`${SOURCE_NAME[source]} bits as a ${side} by ${side} picture`}
        />
      </div>
    </Panel>
  )
}

/** The bits each attacker never saw, with its guesses; pick the stream. */
export function NextBitsPanel({
  placement = 'inline',
  className,
  delay,
  perRow = 25,
}: PanelPlacement & { perRow?: number }) {
  const [source, setSource] = useState<Source>('classical')
  const next = stream[source].next_bits
  return (
    <Panel
      placement={placement}
      className={className}
      delay={delay}
      title="What the attacker guessed"
      description={
        <>
          The first <Num>{count(next.bits.length)}</Num> bits the attacker never saw. A bar marks each bit it
          guessed right; misses are grey.
        </>
      }
      controls={<SourcePicker value={source} onChange={setSource} />}
    >
      <BitStream
        key={source}
        source={source}
        bits={next.bits}
        predictions={next.attacker_predictions}
        perRow={perRow}
        duration={800}
        label={`${SOURCE_NAME[source]}: the next ${next.bits.length} bits and the attacker's guesses`}
      />
    </Panel>
  )
}

/** Min-entropy of both streams on the 0 to 1 bit gauge. */
export function MinEntropyPanel({ placement = 'inline', className, delay }: PanelPlacement) {
  return (
    <Panel
      placement={placement}
      className={className}
      delay={delay}
      title="How unpredictable each stream is"
      description="Min-entropy against each attacker, from 0 bits (fully predictable) to 1 bit (a coin flip). The tick is the conservative bound."
    >
      <div className="panel-gauges">
        {SOURCES.map((s, i) => {
          const a = stream[s].attacker
          return (
            <Gauge
              key={s}
              source={s}
              value={a.min_entropy}
              conservative={a.min_entropy_conservative}
              label={SOURCE_NAME[s]}
              detail={
                <>
                  conservative <Num>{fixed(a.min_entropy_conservative, 3)}</Num>
                </>
              }
              showScale={i === SOURCES.length - 1}
              delay={150 * i}
            />
          )
        })}
      </div>
    </Panel>
  )
}

/** Each attacker's running accuracy, with the final 95% interval; pick the stream. */
export function AccuracyPanel({
  placement = 'inline',
  className,
  delay,
  chartWidth = 640,
  chartHeight = 480,
}: PanelPlacement & { chartWidth?: number; chartHeight?: number }) {
  const [source, setSource] = useState<Source>('quantum')
  const a = stream[source].attacker
  const last = a.running.n_bits[a.running.n_bits.length - 1]
  return (
    <Panel
      placement={placement}
      className={className}
      delay={delay}
      title="The attacker's score as it goes"
      description={
        <>
          Share of bits guessed right, over <Num>{count(a.n_predicted)}</Num> bits the attacker never saw.
          Final: <Num>{percent(a.accuracy, 2)}</Num>, 95% interval{' '}
          <Num>{percentRange(a.ci_low, a.ci_high, 2)}</Num>.
        </>
      }
      controls={<SourcePicker value={source} onChange={setSource} />}
    >
      <LineChart
        key={source}
        title={`Running accuracy of the ${SOURCE_NAME[source].toLowerCase()} attacker, from 0 to 100 percent`}
        width={chartWidth}
        height={chartHeight}
        series={[{ id: source, source, label: SOURCE_NAME[source], x: a.running.n_bits, y: a.running.accuracy }]}
        bands={[
          {
            id: `${source}-ci`,
            source,
            x: [0, last],
            low: [a.ci_low, a.ci_low],
            high: [a.ci_high, a.ci_high],
            label: '95% interval',
          },
        ]}
        references={[{ y: 0.5, label: 'a coin flip' }]}
        yDomain={[0, 1]}
        yTicks={[0, 0.5, 1]}
        formatY={(v) => percent(v, 0)}
        formatX={(v) => (v === 0 ? '0' : `${v / 1000}k`)}
        xLabel="bits predicted"
        yLabel="guessed right"
      />
    </Panel>
  )
}
