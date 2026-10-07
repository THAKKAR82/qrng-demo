// The optional live run on the Machines panel (SPEC.md, Sections 6.4 and 9.5). Rendered
// only behind __QRNG_LIVE__ and only when the page is served by an armed live server. The
// button is an ordinary button with no key of its own, so it can't clash with the deck's
// keys or M.

import { demo, isSynthetic } from '../data/demo'
import { count, utcDate } from '../lib/format'
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

function JobId({ id }: { id: string | null }) {
  return id === null ? null : (
    <>
      {' '}
      Job <Num>{id}</Num>.
    </>
  )
}

/** What the live run is doing, one stage at a time, with the job ID as soon as it exists. */
export function LiveRunStatus({ live }: { live: LiveView }) {
  if (!live.available) {
    return null
  }
  let line = null
  if (live.phase === 'running') {
    const backend = live.health?.backend ?? 'IBM Quantum'
    switch (live.stage) {
      case 'submitting':
        line = <>Sending a job to IBM Quantum {backend}.</>
        break
      case 'submitted':
        line = (
          <>
            Sent to {backend}, waiting for IBM's queue.
            <JobId id={live.jobId} />
          </>
        )
        break
      case 'queued':
        line = (
          <>
            Waiting in IBM's queue{live.elapsedSeconds !== null && <>: <Num>{clock(live.elapsedSeconds)}</Num></>}.
            <JobId id={live.jobId} />
          </>
        )
        break
      case 'running':
        line = (
          <>
            Running on {backend} now.
            <JobId id={live.jobId} />
          </>
        )
        break
      default:
        line = null
    }
  } else if (live.phase === 'done' && live.result !== null) {
    line = (
      <>
        Fresh bits from {live.result.backend} are playing on the quantum machine.{' '}
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
            <span className="term">
              Job <Num>{live.jobId}</Num> may still finish on IBM.
            </span>
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
        Fresh from <span className="num">{result.backend}</span>, {utcDate(result.completedUtc)}:
      </span>{' '}
      job <span className="num">{result.jobId}</span>, <span className="num">{count(result.nQubits)}</span> qubits ×{' '}
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

/** Presenter notes for slide 3, shown only when this page is served by an armed live server. */
export function LiveNotes() {
  const live = useLiveRun()
  if (!live.available) {
    return null
  }
  const health = live.health
  return (
    <p>
      Live run (the live server is armed on <Num>{health?.backend ?? 'IBM Quantum'}</Num>
      {health !== null && health.n_qubits !== null && health.shots !== null && (
        <>
          , <Num>{count(health.n_qubits)}</Num> qubits × <Num>{count(health.shots)}</Num> shots per run,{' '}
          <Num>{count(health.runs_remaining)}</Num> left
        </>
      )}
      ): the button under the machines sends one small job and shows each stage with its job ID. If the panel falls back
      after two minutes, or the run fails, carry on with the recorded run. The job may still finish on IBM; the server
      saves it on this laptop if it does, but the slide keeps the recorded run. Live numbers are noisy: quote the
      headline numbers from the full run.
    </p>
  )
}
