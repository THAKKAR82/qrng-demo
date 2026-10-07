import { demo } from '../data/demo'
import { fixed, percentRange } from '../lib/format'
import { SOURCES } from '../lib/sources'
import { BigNumber } from '../primitives/BigNumber'
import { Gauge } from '../primitives/Gauge'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { MACHINE_NAME } from './machines'
import type { PanelBaseProps } from './shared'
import './panels.css'

const { copy } = demo

/**
 * Min-entropy against each attacker: the headline measure of unpredictability. The two
 * numbers, their ranges and conservative values, all from demo.json.
 */
export function UnpredictabilityPanel({ className, hideHeader, delay = 0 }: PanelBaseProps) {
  return (
    <Panel
      className={className}
      hideHeader={hideHeader}
      delay={delay}
      title="Genuine surprise per bit"
      description="How many bits of genuine surprise each bit contains, for someone trying to predict it. 1 bit is a fair coin; 0 bits means the attacker always knows."
    >
      <div className="unpredictability">
        <div className="unpredictability__numbers">
          {SOURCES.map((source, i) => {
            const a = demo[source].attacker
            return (
              <BigNumber
                key={source}
                source={source}
                value={fixed(a.min_entropy, 3)}
                unit=" bits"
                label={MACHINE_NAME[source]}
                detail={
                  <>
                    95% range <Num>{fixed(a.min_entropy_conservative, 3)}</Num>–<Num>{fixed(a.min_entropy_high, 3)}</Num>{' '}
                    bits
                    <span className="term">
                      {' '}
                      attacker right <Num>{percentRange(a.ci_low, a.ci_high, 2)}</Num> of the time
                    </span>
                  </>
                }
                delay={delay + 150 * i}
              />
            )
          })}
        </div>
        <div className="unpredictability__gauges">
          {SOURCES.map((source, i) => {
            const a = demo[source].attacker
            return (
              <Gauge
                key={source}
                source={source}
                value={a.min_entropy}
                conservative={a.min_entropy_conservative}
                label={MACHINE_NAME[source]}
                detail={
                  <>
                    conservative <Num>{fixed(a.min_entropy_conservative, 3)}</Num> (the tick)
                  </>
                }
                showScale={i === SOURCES.length - 1}
                delay={delay + 300 + 150 * i}
              />
            )
          })}
        </div>
        <p className="unpredictability__verdict reveal">{copy.unpredictability_comparison}</p>
        <p className="term unpredictability__formula">
          Min-entropy H<sub>∞</sub> = −log₂ max(p, 1 − p), where p is the share of unseen bits the attacker guessed right.
          The range comes from the 95% interval for p; the conservative value is its lower end. It measures surprise
          against these attackers, not a guarantee against every possible one.
        </p>
      </div>
    </Panel>
  )
}
