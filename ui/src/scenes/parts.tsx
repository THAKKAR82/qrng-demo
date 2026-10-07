// Pieces shared by several slides: the phone invitation and recurring presenter notes.

import { demo, isSynthetic } from '../data/demo'
import { audienceUrl } from '../lib/audienceUrl'
import { count, percent, percentRange, utcDate } from '../lib/format'
import { revealDelay } from '../lib/motion'
import { QrCode } from '../panels/QrCode'
import { Num } from '../primitives/Num'

const { metadata: meta, cross_checks: checks } = demo
const url = audienceUrl()

/** The phone invitation: QR code and short address, or nothing when no URL is set. */
export function PhoneInvite({ heading }: { heading: string }) {
  if (url === null) {
    return null
  }
  return (
    <aside className="invite reveal" style={revealDelay(200)}>
      <div className="invite__code">
        <QrCode value={url.href} label={`QR code for ${url.short}`} />
      </div>
      <p className="invite__heading">{heading}</p>
      <p className="invite__url num">{url.short}</p>
      <p className="term">Your phone gets its own copy of the app. It isn't connected to this screen.</p>
    </aside>
  )
}

export function CrossCheckNotes() {
  return (
    <>
      <p>
        Fairness cross-checks (each attacker on the other machine): the classical machine's attacker scored{' '}
        <Num>{percent(checks.mt_on_quantum.accuracy, 2)}</Num> on the quantum bits (95%{' '}
        <Num>{percentRange(checks.mt_on_quantum.ci_low, checks.mt_on_quantum.ci_high, 2)}</Num>); the quantum
        machine's attacker scored <Num>{percent(checks.bias_on_classical.accuracy, 2)}</Num> on the classical bits (95%{' '}
        <Num>{percentRange(checks.bias_on_classical.ci_low, checks.bias_on_classical.ci_high, 2)}</Num>).
        {checks.mt_on_quantum.consistent_with_half && checks.bias_on_classical.consistent_with_half
          ? ' Both intervals include 50%: neither attacker was tuned to make one machine look bad.'
          : ' At least one interval misses 50%; with 95% intervals that happens about one time in twenty by chance.'}
      </p>
    </>
  )
}

export function RunNote() {
  if (isSynthetic || meta.backend === null) {
    return (
      <p>
        <strong>This deck is showing synthetic sample data ({meta.run_folder}), not quantum hardware output.</strong> Say
        so out loud.
      </p>
    )
  }
  return (
    <p>
      Data: IBM Quantum <Num>{meta.backend}</Num>, job <Num>{meta.job_id ?? 'unknown'}</Num>
      {meta.date_utc !== null && <>, completed {utcDate(meta.date_utc)}</>}; <Num>{count(meta.n_qubits)}</Num> qubits ×{' '}
      <Num>{count(meta.shots)}</Num> shots
      {meta.qubits_selected_by_readout_error && meta.qubit_selection_candidates !== null && (
        <>
          , qubits picked for lowest readout error from <Num>{count(meta.qubit_selection_candidates)}</Num>
        </>
      )}
      .
    </p>
  )
}
