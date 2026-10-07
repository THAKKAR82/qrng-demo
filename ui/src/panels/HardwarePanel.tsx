import { useRef, useState, type ChangeEvent, type MouseEvent } from 'react'
import { demo } from '../data/demo'
import type { QubitResult } from '../data/types'
import { count, fixed, percent } from '../lib/format'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'
import type { PanelBaseProps } from './shared'
import './panels.css'

const { layout, metadata: meta, quantum, copy } = demo

/** Padding around the outermost qubits, in grid units. */
const PAD = 0.7
/** A tap selects the nearest qubit within this distance, in grid units. */
const PICK_RADIUS = 0.75

type Zoom = '1' | '2'
const ZOOMS: readonly Segment<Zoom>[] = [
  { value: '1', label: '1×' },
  { value: '2', label: '2×' },
]

/** Results for each physical qubit used in the run. */
const byPhysical = new Map<number, QubitResult>(
  quantum.qubits.filter((q) => q.physical_qubit !== null).map((q) => [q.physical_qubit as number, q]),
)
/** The most lopsided qubit's distance from 50/50 sets the darkest shade. */
const maxBias = quantum.bias_summary.worst.abs_bias

/** Shade for a used qubit: paler near 50/50, deeper when lopsided (25% to 100% of the hue). */
function shade(q: QubitResult): string {
  const strength = maxBias > 0 ? Math.abs(q.p_one - 0.5) / maxBias : 0
  return `color-mix(in srgb, var(--color-quantum-mark) ${Math.round(25 + 75 * strength)}%, var(--color-surface))`
}

/**
 * The device's qubits from Qiskit's bundled description: the ones used in the run coloured
 * by how lopsided they read, flagged ones ringed. Tap or click anywhere to select the
 * nearest qubit; on phones the map zooms and scrolls sideways.
 */
export function HardwarePanel({ placement = 'inline', className,
  hideHeader, delay }: PanelBaseProps) {
  const [selected, setSelected] = useState<number | null>(quantum.bias_summary.worst.physical_qubit)
  const [zoom, setZoom] = useState<Zoom>('1')
  const svgRef = useRef<SVGSVGElement>(null)

  if (layout === null) {
    return (
      <Panel placement={placement} className={className} delay={delay} title="The chip">
        <div className="hardware hardware--none">
          <p className="is-muted">
            There is no device layout for this data
            {meta.backend === null ? ' (it is sample data, not from a real chip)' : ` (Qiskit ships no description of ${meta.backend})`}.
          </p>
        </div>
      </Panel>
    )
  }

  const xs = layout.coordinates.map((c) => c[0])
  const ys = layout.coordinates.map((c) => c[1])
  const minX = Math.min(...xs) - PAD
  const minY = Math.min(...ys) - PAD
  const width = Math.max(...xs) - Math.min(...xs) + 2 * PAD
  const height = Math.max(...ys) - Math.min(...ys) + 2 * PAD

  const pick = (event: MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current
    const matrix = svg?.getScreenCTM()
    if (svg == null || matrix == null) {
      return
    }
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    let best = -1
    let bestDistance = PICK_RADIUS
    for (let q = 0; q < layout.coordinates.length; q += 1) {
      const [x, y] = layout.coordinates[q]
      const d = Math.hypot(x - point.x, y - point.y)
      if (d <= bestDistance) {
        best = q
        bestDistance = d
      }
    }
    if (best >= 0) {
      setSelected(best)
    }
  }

  const used = [...byPhysical.keys()].sort((a, b) => a - b)
  const flagged = quantum.bias_tests.flagged_physical_qubits.filter((q): q is number => q !== null)
  const chosen = selected === null ? undefined : byPhysical.get(selected)

  return (
    <Panel
      placement={placement}
      className={className}
      hideHeader={hideHeader}
      delay={delay}
      title={`The chip: ${meta.backend ?? 'the device'}'s ${count(layout.num_qubits)} qubits`}
      description={
        <>
          The <Num>{count(used.length)}</Num> qubits used are coloured: deeper means further from reading 0 and 1 equally
          often. Ringed qubits were flagged as biased. Tap or click a qubit for its numbers.
        </>
      }
      controls={
        <div className="panel-row">
          <label className="hardware__select">
            <span className="sr-only">Choose a qubit</span>
            <select
              value={selected ?? ''}
              onChange={(e: ChangeEvent<HTMLSelectElement>) => setSelected(e.target.value === '' ? null : Number(e.target.value))}
            >
              <option value="">Choose a qubit…</option>
              {used.map((q) => (
                <option key={q} value={q}>
                  Qubit {q}
                  {flagged.includes(q) ? ' (flagged)' : ''}
                </option>
              ))}
            </select>
          </label>
          {placement === 'standalone' && <SegmentedControl label="Zoom" segments={ZOOMS} value={zoom} onChange={setZoom} />}
        </div>
      }
    >
      <div className="hardware">
        <div className="hardware__scroll">
          <svg
            ref={svgRef}
            className="hardware__map"
            style={{ width: `${Number(zoom) * 100}%` }}
            viewBox={`${minX} ${minY} ${width} ${height}`}
            role="img"
            aria-label={`Map of ${count(layout.num_qubits)} qubits; ${count(used.length)} used in the run are coloured`}
            onClick={pick}
          >
            <g className="hardware__edges">
              {layout.edges.map(([a, b]) => (
                <line
                  key={`${a}-${b}`}
                  x1={layout.coordinates[a][0]}
                  y1={layout.coordinates[a][1]}
                  x2={layout.coordinates[b][0]}
                  y2={layout.coordinates[b][1]}
                />
              ))}
            </g>
            {layout.coordinates.map(([x, y], q) => {
              const result = byPhysical.get(q)
              const isSelected = q === selected
              return (
                <g key={q} data-qubit={q} className="hardware__qubit">
                  {result === undefined ? (
                    <circle cx={x} cy={y} r={0.16} className="hardware__unused" />
                  ) : (
                    <circle cx={x} cy={y} r={0.3} style={{ fill: shade(result) }} className="hardware__used" />
                  )}
                  {result?.flagged === true && <circle cx={x} cy={y} r={0.42} className="hardware__flag" />}
                  {isSelected && <circle cx={x} cy={y} r={0.5} className="hardware__selected" />}
                </g>
              )
            })}
          </svg>
        </div>
        <div className="hardware__details" aria-live="polite">
          <Details qubit={selected} result={chosen} />
          <p className="hardware__note">{copy.bias_note}</p>
          <p className="term">
            Flagged qubits were kept, not removed: every bit they produced is in the data. Flagged means its share of 1s
            sits more than <Num>{fixed(quantum.bias_tests.z_threshold, 0)}</Num> standard errors from half (z-score).
          </p>
          <p className="term">
            Layout: {layout.description} ({layout.device}, qiskit-ibm-runtime {layout.qiskit_ibm_runtime_version}), not
            live calibration. Readout errors are from the run's own calibration.
          </p>
        </div>
      </div>
    </Panel>
  )
}

function Details({ qubit, result }: { qubit: number | null; result: QubitResult | undefined }) {
  if (qubit === null) {
    return <p className="is-muted">No qubit selected.</p>
  }
  if (result === undefined) {
    return (
      <div className="hardware__chosen">
        <p className="hardware__name">
          Qubit <Num>{qubit}</Num>
        </p>
        <p className="is-muted">Not used in this run.</p>
      </div>
    )
  }
  return (
    <div className="hardware__chosen">
      <p className="hardware__name">
        Qubit <Num>{qubit}</Num>
        {result.flagged && <span className="hardware__flagged"> flagged</span>}
      </p>
      <dl className="hardware__facts">
        <div>
          <dt>Reads 1</dt>
          <dd className="num is-quantum">{percent(result.p_one, 1)}</dd>
          <dd className="term">of the time, P(1)</dd>
        </div>
        <div>
          <dt>Misreads</dt>
          <dd className="num is-quantum">{result.readout_error === null ? 'unknown' : percent(result.readout_error, 2)}</dd>
          <dd className="term">readout error</dd>
        </div>
        <div>
          <dt>Distance from half</dt>
          <dd className="num is-quantum">{fixed(result.z, 1)}</dd>
          <dd className="term">z-score</dd>
        </div>
      </dl>
    </div>
  )
}
