import { useState } from 'react'
import { demo } from '../data/demo'
import type { Source } from '../data/types'
import { usePanelKeys } from '../deck/usePanelKeys'
import { count, fixed } from '../lib/format'
import { useSessionNumber } from '../lib/session'
import { Bitmap } from '../primitives/Bitmap'
import { Gauge } from '../primitives/Gauge'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { MACHINE_NAME } from './machines'
import { ActionButton, type PanelBaseProps } from './shared'
import './panels.css'

const { classical, quantum, copy } = demo

/** Shannon entropy shown for each machine: pooled for classical, per-qubit mean for quantum. */
const SHANNON: Record<Source, { value: number; detail: string }> = {
  classical: { value: classical.shannon_entropy.pooled, detail: 'all bits together' },
  quantum: { value: quantum.shannon_entropy.per_qubit_mean, detail: 'average per qubit' },
}

interface TellApartPanelProps extends PanelBaseProps {
  /** Reveal driven from outside, such as a slide step. The panel's own button and R still work. */
  revealed?: boolean
  /** Show the two ordinary-statistics gauges (a later slide step). */
  showGauges?: boolean
  /** Show the gauges as soon as the pictures are revealed (phones, with no slide steps). */
  gaugesOnReveal?: boolean
}

/**
 * Two unlabelled pictures of bits, one from each machine, in an order picked at random for
 * the session, drawn in the same ink so colour gives nothing away. A reveal names them.
 */
export function TellApartPanel({
  className,
  hideHeader,
  delay,
  keyboard = false,
  revealed: revealedFromStep = false,
  showGauges: showGaugesFromStep = false,
  gaugesOnReveal = false,
}: TellApartPanelProps) {
  // 0: classical on the left; 1: quantum on the left. Kept for the session.
  const [flip] = useSessionNumber('tell-apart:order', () => (Math.random() < 0.5 ? 0 : 1))
  const order: readonly Source[] = flip === 0 ? ['classical', 'quantum'] : ['quantum', 'classical']
  const [revealedHere, setRevealedHere] = useState(false)
  const revealed = revealedHere || revealedFromStep || showGaugesFromStep
  const showGauges = showGaugesFromStep || (gaugesOnReveal && revealed)
  usePanelKeys({ r: () => setRevealedHere(true) }, keyboard)

  const side = classical.bitmap.size
  return (
    <Panel
      className={className}
      hideHeader={hideHeader}
      delay={delay}
      title="Which picture came from which machine?"
      description={
        <>
          The first <Num>{count(side * side)}</Num> bits from each machine, one square per bit, both drawn in black so
          colour gives nothing away.
        </>
      }
      controls={
        <ActionButton variant="primary" onClick={() => setRevealedHere(true)} disabled={revealed}>
          {revealed ? 'Revealed' : 'Reveal'}
        </ActionButton>
      }
    >
      <div className={`tell-apart${showGauges ? ' tell-apart--with-gauges' : ''}`}>
        <div className="tell-apart__pictures">
          {order.map((source, i) => (
            <figure key={source} className="tell-apart__picture">
              <Bitmap
                source={source}
                tone={revealed ? 'source' : 'neutral'}
                bitmap={demo[source].bitmap}
                label={revealed ? `${MACHINE_NAME[source]}: ${side} by ${side} bits` : `Picture ${'AB'[i]}: ${side} by ${side} bits`}
              />
              <figcaption className="tell-apart__caption" aria-live="polite">
                {revealed ? (
                  <span className={`reveal is-${source}`}>{MACHINE_NAME[source]}</span>
                ) : (
                  <span>Picture {'AB'[i]}</span>
                )}
              </figcaption>
            </figure>
          ))}
        </div>
        {showGauges && (
          <div className="tell-apart__gauges">
            <p className="tell-apart__verdict reveal">{copy.shannon_comparison}</p>
            {order.map((source, i) => (
              <Gauge
                key={source}
                source={source}
                value={SHANNON[source].value}
                label={MACHINE_NAME[source]}
                detail={SHANNON[source].detail}
                delay={200 + 150 * i}
              />
            ))}
            <p className="term reveal">
              Shannon entropy, bits per bit: how evenly 1s and 0s are mixed, from <Num>0</Num> (all the same) to{' '}
              <Num>1</Num> (perfectly balanced). Classical <Num>{fixed(SHANNON.classical.value, 5)}</Num>, quantum{' '}
              <Num>{fixed(SHANNON.quantum.value, 5)}</Num>.
            </p>
          </div>
        )}
      </div>
    </Panel>
  )
}
