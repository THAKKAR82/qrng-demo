// Small panels for the primitives page, built from the primitives with real data from
// demo.json. The talk's own panels are in src/panels/. They describe the data; they make
// no comparative claims (SPEC.md, Section 4.3).

import { useState } from 'react'
import { demo } from '../data/demo'
import { poolPreview } from '../lib/preview'
import type { Source } from '../data/types'
import { count } from '../lib/format'
import { SOURCE_NAME } from '../lib/sources'
import { Bitmap } from '../primitives/Bitmap'
import { BitStream } from '../primitives/BitStream'
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

interface PanelPlacement {
  className?: string
  delay?: number
}

function SourcePicker({ value, onChange }: { value: Source; onChange: (s: Source) => void }) {
  return <SegmentedControl label="Stream" segments={SOURCE_SEGMENTS} value={value} onChange={onChange} />
}

/** The first bits of one stream as a picture; pick the stream. */
export function BitmapPanel({ className, delay }: PanelPlacement) {
  const [source, setSource] = useState<Source>('quantum')
  const side = stream[source].bitmap.size
  return (
    <Panel
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
  className,
  delay,
  perRow = 25,
}: PanelPlacement & { perRow?: number }) {
  const [source, setSource] = useState<Source>('classical')
  const next = poolPreview(source)
  return (
    <Panel
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
