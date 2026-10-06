import { useEffect } from 'react'
import { demo, isSynthetic } from '../data/demo'
import { SyntheticLabel } from '../deck/SyntheticLabel'
import { count, utcDate } from '../lib/format'
import { AccuracyPanel, BitmapPanel, MinEntropyPanel, NextBitsPanel } from '../pages/panels'
import './AudienceView.css'

const { metadata: meta } = demo

/** Where the data came from, in one or two plain lines. Every value is from demo.json. */
function RunLine() {
  const hardware = meta.source === 'ibm_quantum_hardware' && !isSynthetic
  return (
    <div className="audience__run">
      <p>
        {hardware && meta.backend !== null ? (
          <>
            Measured on IBM Quantum <span className="num">{meta.backend}</span>
          </>
        ) : (
          <>
            Sample data <span className="num">{meta.run_folder}</span>
          </>
        )}
        {meta.date_utc !== null && <>, {utcDate(meta.date_utc)}</>}
      </p>
      <p className="is-muted">
        <span className="num">{count(meta.n_qubits)}</span> qubits,{' '}
        <span className="num">{count(meta.shots)}</span> shots
        {meta.qubits_selected_by_readout_error && meta.qubit_selection_candidates !== null && (
          <>
            ; qubits picked for lowest readout error from{' '}
            <span className="num">{count(meta.qubit_selection_candidates)}</span>
          </>
        )}
      </p>
    </div>
  )
}

/**
 * The audience's phone view, in explore mode: the same data and panels as the talk, to
 * browse freely. It runs from a static hosted copy and is not connected to the
 * presenter's app; participation in the talk is in person (SPEC.md, Section 9.1).
 */
export function AudienceView() {
  useEffect(() => {
    document.title = 'QRNG demo'
  }, [])

  return (
    <div className="audience">
      {isSynthetic && <SyntheticLabel placement="page" />}
      <header className="audience__header">
        <h1 className="audience__title">Quantum and classical random bits</h1>
        <RunLine />
      </header>
      <main className="audience__panels">
        <MinEntropyPanel placement="standalone" />
        <AccuracyPanel placement="standalone" chartWidth={440} chartHeight={400} delay={80} />
        <NextBitsPanel placement="standalone" perRow={20} delay={160} />
        <BitmapPanel placement="standalone" delay={240} />
      </main>
    </div>
  )
}
