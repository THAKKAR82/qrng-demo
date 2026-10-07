// The optional live run on the Machines panel (SPEC.md, Sections 6.4 and 9.5). Rendered
// only behind __QRNG_LIVE__ and only when the page is served by an armed live server. The
// button is an ordinary button with no key of its own, so it can't clash with the deck's
// keys or M.

import { demo, isSynthetic } from '../data/demo'
import { count, ibmQuantumComputer, utcDate } from '../lib/format'
import { startLiveRun, useLiveRun, type LiveResult, type LiveView } from '../lib/live'
import { Num } from '../primitives/Num'
import { ActionButton } from './shared'

const { metadata: meta } = demo

/** "the run from 6 October 2026, 01:35 UTC": the recorded run the panel falls back to. */
function recordedRun(): string {
  if (isSynthetic || meta.date_utc === null) {
    return 'the recorded sample data'
  }
  return `the run from ${utcDate(meta.date_utc)}`
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export function LiveRunButton({ live }: { live: LiveView }) {
  if (!live.available || (!live.canStart && live.phase !== 'running')) {
    return null
  }
  return (
    <ActionButton onClick={() => void startLiveRun()} disabled={!live.canStart}>
      Run on real quantum hardware now
    </ActionButton>
  )
}

/**
 * What the live run is doing, one stage at a time. The screen names the machine by its size
 * and never shows the job ID or backend name (SPEC.md, Section 4.8); the notes have them.
 */
export function LiveRunStatus({ live }: { live: LiveView }) {
  if (!live.available) {
    return null
  }
  let line = null
  if (live.phase === 'running') {
    switch (live.stage) {
      case 'submitting':
        line = <>Sending a job to {ibmQuantumComputer(live.health?.backend_num_qubits ?? null)}.</>
        break
      case 'submitted':
        line = <>Sent. Waiting for IBM's queue.</>
        break
      case 'queued':
        line = (
          <>
            Waiting in IBM's queue{live.elapsedSeconds !== null && <>: <Num>{clock(live.elapsedSeconds)}</Num></>}.
          </>
        )
        break
      case 'running':
        line = <>Running on the quantum computer now.</>
        break
      default:
        line = null
    }
  } else if (live.phase === 'done' && live.result !== null) {
    line = (
      <>
        Fresh bits from {ibmQuantumComputer(live.result.backendQubits)} are playing on the quantum machine.{' '}
        <span className="term">
          A live run is small (<Num>{count(live.result.nBits)}</Num> bits), so its numbers are noisy; the headline numbers
          come from the full run.
        </span>
      </>
    )
  } else if (live.phase === 'fallback') {
    line = (
      <>
        {live.fallback === 'timeout' ? "IBM's queue is busy" : "The live run didn't finish"}; showing {recordedRun()}.
        {live.jobId !== null && (
          <>
            {' '}
            <span className="term">The job may still finish on IBM.</span>
          </>
        )}
      </>
    )
  }
  if (line === null && live.notice === null) {
    return null
  }
  return (
    <p className="live-run" aria-live="polite" data-live-phase={live.phase}>
      {line}
      {live.notice !== null && (
        <>
          {line !== null && ' '}
          <span className="live-run__notice">{live.notice}</span>
        </>
      )}
    </p>
  )
}

/** The live job in place of the recorded run's facts under the quantum machine. */
export function LiveRunFacts({ result }: { result: LiveResult }) {
  return (
    <p className="run-facts">
      <span className="run-facts__label">
        Fresh from {ibmQuantumComputer(result.backendQubits)}, {utcDate(result.completedUtc)}:
      </span>{' '}
      <span className="num">{count(result.nQubits)}</span> qubits ×{' '}
      <span className="num">{count(result.shots)}</span> shots
      {result.selectedFrom !== null && (
        <>
          {' '}
          <span className="run-facts__detail">
            (qubits picked for lowest readout error from <span className="num">{count(result.selectedFrom)}</span>)
          </span>
        </>
      )}
      .
    </p>
  )
}

/**
 * Presenter notes for slide 3, shown only when this page is served by an armed live server.
 * They carry what the screen leaves out (SPEC.md, Section 4.8): the backend and, as soon as
 * it exists, the live job's ID, so the presenter can answer "did it really run?".
 */
export function LiveNotes() {
  const live = useLiveRun()
  if (!live.available) {
    return null
  }
  const health = live.health
  const backend = live.result?.backend ?? health?.backend ?? null
  return (
    <>
      <p>
        Live run (the live server is armed on <Num>{health?.backend ?? 'IBM Quantum'}</Num>
        {health !== null && health.n_qubits !== null && health.shots !== null && (
          <>
            , <Num>{count(health.n_qubits)}</Num> qubits × <Num>{count(health.shots)}</Num> shots per run,{' '}
            <Num>{count(health.runs_remaining)}</Num> left
          </>
        )}
        ): the button under the machines sends one small job and shows each stage. If the panel falls back after two
        minutes, or the run fails, carry on with the recorded run. The job may still finish on IBM; the server saves it on
        this laptop if it does, but the slide keeps the recorded run. Live numbers are noisy: quote the headline numbers
        from the full run.
      </p>
      {live.jobId !== null && (
        <p>
          This live run: job <Num>{live.jobId}</Num>
          {backend !== null && (
            <>
              {' '}
              on <Num>{backend}</Num>
            </>
          )}
          {live.result !== null && <>, completed {utcDate(live.result.completedUtc)}</>}. The screen shows neither; read
          them out if someone asks how we know it ran.
        </p>
      )}
    </>
  )
}
