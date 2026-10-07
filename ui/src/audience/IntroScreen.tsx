import { demo, isSynthetic } from '../data/demo'
import type { Screen } from './names'
import { PhoneButton, PhoneScreen } from './parts'

/** The first screen: what this is, in one sentence, and the two games. */
export function IntroScreen({ go }: { go: (screen: Screen) => void }) {
  const real = !isSynthetic && demo.metadata.backend !== null
  return (
    <PhoneScreen id="intro" title="Can you beat a quantum computer?">
      <p className="phone-lead">
        {real
          ? 'Two machines made random bits: one runs an ordinary computer formula, the other is a real IBM quantum computer.'
          : 'Two machines made random bits: one runs an ordinary computer formula, and sample data stands in for a quantum computer.'}
      </p>
      <div className="phone-actions phone-actions--games">
        <PhoneButton variant="big" onClick={() => go('spot')}>
          Spot the quantum machine
        </PhoneButton>
        <PhoneButton variant="big" onClick={() => go('beat')}>
          Beat the attacker
        </PhoneButton>
      </div>
    </PhoneScreen>
  )
}
