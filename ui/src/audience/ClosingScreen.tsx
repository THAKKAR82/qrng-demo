import type { Screen } from './names'
import { PhoneButton, PhoneScreen, RunFacts } from './parts'

/** The takeaway, with the real run's details in small text. */
export function ClosingScreen({ go }: { go: (screen: Screen) => void }) {
  return (
    <PhoneScreen id="end" title="What it all means">
      <p className="phone-lead">
        Quantum randomness is guaranteed by physics: nothing inside a qubit decides its outcome in advance, so there is no
        hidden pattern for an attacker to learn.
      </p>
      <p className="phone-small">
        Good classical generators, like the secure one built into your phone, are unpredictable in practice too. The
        formula in these games is Python's everyday default, not the strongest classical option.
      </p>
      <RunFacts />
      <div className="phone-actions">
        <PhoneButton variant="primary" onClick={() => go('intro')}>
          Back to the games
        </PhoneButton>
      </div>
    </PhoneScreen>
  )
}
