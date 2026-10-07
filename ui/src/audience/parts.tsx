// Small pieces shared by the phone screens.

import type { MouseEvent, ReactNode } from 'react'
import { demo, isSynthetic } from '../data/demo'
import type { Source } from '../data/types'
import { ibmQuantumComputer, utcDate } from '../lib/format'

interface PhoneButtonProps {
  children: ReactNode
  onClick: () => void
  variant?: 'primary' | 'secondary' | 'big'
  source?: Source
  disabled?: boolean
  label?: string
}

/** A large tap target (at least 48 CSS px). It drops focus after a tap so nothing stays highlighted. */
export function PhoneButton({ children, onClick, variant = 'secondary', source, disabled, label }: PhoneButtonProps) {
  const handle = (event: MouseEvent<HTMLButtonElement>) => {
    onClick()
    if (event.detail > 0) {
      event.currentTarget.blur()
    }
  }
  const tone = source === undefined ? '' : ` phone-button--${source}`
  return (
    <button
      type="button"
      className={`phone-button phone-button--${variant}${tone}`}
      onClick={handle}
      disabled={disabled}
      aria-label={label}
    >
      {children}
    </button>
  )
}

/** One screen: a heading and its content, in normal page flow. */
export function PhoneScreen({ title, children, id }: { title: ReactNode; children: ReactNode; id: string }) {
  return (
    <main className="phone-screen" data-screen={id}>
      <h1 className="phone-screen__title">{title}</h1>
      {children}
    </main>
  )
}

/** The real run behind the quantum bits, in small text (SPEC.md, Section 4.8); or a sample-data note. */
export function RunFacts() {
  const meta = demo.metadata
  if (isSynthetic || meta.backend === null) {
    return (
      <p className="phone-small">
        These games use synthetic sample data (<span className="num">{meta.run_folder}</span>), not quantum hardware
        output.
      </p>
    )
  }
  return (
    <p className="phone-small">
      The quantum bits: run on {ibmQuantumComputer(meta.backend_num_qubits)}
      {meta.date_utc !== null && <>, {utcDate(meta.date_utc)}</>}.
    </p>
  )
}
