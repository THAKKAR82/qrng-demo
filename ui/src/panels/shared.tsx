// Pieces shared by the panels: the machine picker, large action buttons, and the facts
// about the real run. Everything shown comes from demo.json.

import type { MouseEvent, ReactNode } from 'react'
import { demo, isSynthetic } from '../data/demo'
import type { Source } from '../data/types'
import { count, utcDate } from '../lib/format'
import { SegmentedControl, type Segment } from '../primitives/SegmentedControl'

export type Placement = 'inline' | 'standalone'

/** Props every panel takes. */
export interface PanelBaseProps {
  /** "inline" inside a slide; "standalone" in the phone view. */
  placement?: Placement
  className?: string
  delay?: number
  /** Answer the presenter's keys (0, 1, R, C, Q). On in slides, off on phones. */
  keyboard?: boolean
  /** Hide the panel's own title and description (a slide's title and lede replace them). */
  hideHeader?: boolean
}

const MACHINE_SEGMENTS: readonly Segment<Source>[] = [
  { value: 'classical', label: 'Classical', source: 'classical' },
  { value: 'quantum', label: 'Quantum', source: 'quantum' },
]

export function MachinePicker({ value, onChange }: { value: Source; onChange: (s: Source) => void }) {
  return <SegmentedControl label="Machine" segments={MACHINE_SEGMENTS} value={value} onChange={onChange} />
}

interface ActionButtonProps {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  /** "primary" is filled in ink; "big" is a large square key such as a 0 or 1 guess. */
  variant?: 'primary' | 'secondary' | 'big'
  source?: Source
  /** Accessible name when the visible text is not enough, such as "Guess 0". */
  label?: string
}

/**
 * A large button, at least 44 CSS px in both dimensions. Like SegmentedControl, it gives
 * up focus after a tap or click so the presenter's clicker keeps driving the deck.
 */
export function ActionButton({ children, onClick, disabled, variant = 'secondary', source, label }: ActionButtonProps) {
  const handle = (event: MouseEvent<HTMLButtonElement>) => {
    onClick()
    if (event.detail > 0) {
      event.currentTarget.blur()
    }
  }
  const tone = source === undefined ? '' : ` action--${source}`
  return (
    <button
      type="button"
      className={`action action--${variant}${tone}`}
      onClick={handle}
      disabled={disabled}
      aria-label={label}
    >
      {children}
    </button>
  )
}

const { metadata: meta } = demo

/** The real run behind the quantum bits, labelled as such; or a sample-data label. */
export function QuantumRunFacts() {
  if (isSynthetic || meta.backend === null) {
    return (
      <p className="run-facts">
        <span className="run-facts__label">Sample data</span> <span className="num">{meta.run_folder}</span>: synthetic
        bits, not from quantum hardware. <span className="num">{count(meta.n_qubits)}</span> columns,{' '}
        <span className="num">{count(meta.shots)}</span> rows.
      </p>
    )
  }
  return (
    <p className="run-facts">
      <span className="run-facts__label">The actual run:</span> IBM Quantum <span className="num">{meta.backend}</span>
      {meta.job_id !== null && (
        <>
          , job <span className="num">{meta.job_id}</span>
        </>
      )}
      {meta.date_utc !== null && <>, {utcDate(meta.date_utc)}</>}, <span className="num">{count(meta.n_qubits)}</span>{' '}
      qubits × <span className="num">{count(meta.shots)}</span> shots
      {meta.qubits_selected_by_readout_error && meta.qubit_selection_candidates !== null && (
        <>
          {' '}
          <span className="run-facts__detail">
            (qubits picked for lowest readout error from <span className="num">{count(meta.qubit_selection_candidates)}</span>)
          </span>
        </>
      )}
      .
    </p>
  )
}

/** Where the classical bits came from. */
export function ClassicalRunFacts() {
  return (
    <p className="run-facts">
      <span className="run-facts__label">{meta.classical_synthetic ? 'Sample data:' : 'The actual run:'}</span> Python's
      built-in random number generator, seeded once by the operating system.{' '}
      <span className="run-facts__detail">{meta.classical_generator}</span>
    </p>
  )
}
