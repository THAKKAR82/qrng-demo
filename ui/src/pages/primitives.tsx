// The primitives page: every primitive rendered with real data from demo.json, one per
// scene, so the deck engine (navigation, progress, notes, fullscreen) is exercised too.
// Open it with #primitives or ?primitives (both work under file://), or press P.

import { demo } from '../data/demo'
import type { SceneDef } from '../deck/types'
import { count, utcDate } from '../lib/format'
import {
  BigNumberScene,
  BitmapScene,
  BitStreamScene,
  CrossCheckNote,
  GaugeScene,
  LineChartScene,
  PanelScene,
  RunNotes,
  TokensScene,
} from './PrimitiveScenes'

const { metadata: meta, quantum, classical, cross_checks: checks } = demo

export const primitiveScenes: readonly SceneDef[] = [
  {
    id: 'tokens',
    title: 'Design tokens',
    notes: <RunNotes />,
    render: () => <TokensScene />,
  },
  {
    id: 'big-number',
    title: 'BigNumber',
    notes:
      meta.date_utc === null ? undefined : <p>Quantum job completed {utcDate(meta.date_utc)}.</p>,
    render: () => <BigNumberScene />,
  },
  {
    id: 'bit-stream',
    title: 'BitStream',
    notes: (
      <p>
        Classical bits start at bit <span className="num">{count(classical.next_bits.start_bit)}</span>, right
        after the <span className="num">{count(classical.attacker.n_training_bits)}</span> bits the attacker
        saw. Quantum bits start at bit <span className="num">{count(quantum.next_bits.start_bit)}</span>.
      </p>
    ),
    render: () => <BitStreamScene />,
  },
  { id: 'bitmap', title: 'Bitmap', render: () => <BitmapScene /> },
  { id: 'gauge', title: 'Gauge', render: () => <GaugeScene /> },
  {
    id: 'line-chart',
    title: 'LineChart',
    notes: (
      <>
        <p>Cross-checks: each attacker run against the other stream (SPEC.md, Section 3.1).</p>
        <CrossCheckNote check={checks.mt_on_quantum} stream="quantum" />
        <CrossCheckNote check={checks.bias_on_classical} stream="classical" />
      </>
    ),
    render: () => <LineChartScene />,
  },
  {
    id: 'panel',
    title: 'Panel',
    notes: <p>Tap or click a stream. The deck still answers the clicker afterwards: a button gives up focus once it has been tapped or clicked.</p>,
    render: () => <PanelScene />,
  },
]
