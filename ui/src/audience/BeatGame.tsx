import { useState } from 'react'
import { demo, pools } from '../data/demo'
import type { Source } from '../data/types'
import { count } from '../lib/format'
import { readPool, randomStart } from '../lib/pool'
import { useSessionNumber } from '../lib/session'
import { countMatches } from '../lib/stats'
import { OTHER, PHONE_NAME, type Screen } from './names'
import { PhoneButton, PhoneScreen } from './parts'

/** Rounds in one game (SPEC.md, Section 9.6). */
export const BEAT_ROUNDS = 20

interface Game {
  machine: Source
  /** Pool index of this game's first bit. */
  from: number
  guesses: number[]
}

/**
 * "Beat the attacker": pick a machine, then guess the next bit for 20 rounds. Each round
 * reveals the true bit, whether you were right, and what the attacker guessed. Bits come
 * from the held-out pool under the Guess game's rules: a random start once per session,
 * never repeated, stopping at the end of the pool.
 */
export function BeatGame({ go }: { go: (screen: Screen) => void }) {
  const [classicalCursor, setClassicalCursor] = useSessionNumber('guess:classical', () =>
    randomStart(pools.classical.length),
  )
  const [quantumCursor, setQuantumCursor] = useSessionNumber('guess:quantum', () => randomStart(pools.quantum.length))
  const cursorOf = { classical: classicalCursor, quantum: quantumCursor }
  const setCursorOf = { classical: setClassicalCursor, quantum: setQuantumCursor }
  const [game, setGame] = useState<Game | null>(null)

  const start = (machine: Source) => {
    setGame({ machine, from: cursorOf[machine], guesses: [] })
    window.scrollTo({ top: 0 })
  }

  if (game === null) {
    return (
      <PhoneScreen id="beat-pick" title="Beat the attacker">
        <p className="phone-lead">
          Guess the next bit, <span className="num">{BEAT_ROUNDS}</span> times. An attacker that has studied the machine
          guesses too. Pick a machine:
        </p>
        <div className="phone-actions">
          {(['classical', 'quantum'] as const).map((m) => (
            <PhoneButton key={m} variant="big" source={m} onClick={() => start(m)}>
              {PHONE_NAME[m]}
            </PhoneButton>
          ))}
        </div>
      </PhoneScreen>
    )
  }

  const { machine, from, guesses } = game
  const pool = pools[machine]
  const played = guesses.length
  const outOfBits = from + played >= pool.length
  const finished = played >= BEAT_ROUNDS || outOfBits

  const guess = (bit: 0 | 1) => {
    if (finished) {
      return
    }
    readPool(pool, from + played, 1) // bounded: throws rather than wrap
    setGame({ ...game, guesses: [...guesses, bit] })
    setCursorOf[machine](from + played + 1)
  }

  const { bits: truths, predictions } = readPool(pool, from, played)
  const yours = countMatches(guesses, truths, played)
  const attackers = countMatches(predictions, truths, played)

  if (finished) {
    const attacker = demo[machine].attacker
    return (
      <PhoneScreen id="beat-end" title={`Beat the attacker: ${PHONE_NAME[machine].toLowerCase()}`}>
        {outOfBits && played < BEAT_ROUNDS && <p className="phone-lead">End of the recorded bits.</p>}
        <p className="phone-lead">
          You and the attacker guessed the same <span className="num">{count(played)}</span> bits.
        </p>
        <div className="beat-scores" role="status">
          <p className="beat-score">
            <span className="beat-score__who">You</span>
            <span className={`num is-${machine}`}>
              {count(yours)} of {count(played)}
            </span>
          </p>
          <p className="beat-score">
            <span className="beat-score__who">The attacker</span>
            <span className={`num is-${machine}`}>
              {count(attackers)} of {count(played)}
            </span>
          </p>
        </div>
        <p className="phone-lead">
          Over all <span className="num">{count(attacker.n_predicted)}</span> bits it never saw:{' '}
          {machine === 'classical' ? demo.copy.classical_attack : demo.copy.quantum_attack}
        </p>
        <div className="phone-actions">
          <PhoneButton variant="primary" source={OTHER[machine]} onClick={() => start(OTHER[machine])}>
            Try the {PHONE_NAME[OTHER[machine]].toLowerCase()}
          </PhoneButton>
          <PhoneButton onClick={() => go('end')}>What it all means</PhoneButton>
          <PhoneButton onClick={() => go('spot')}>Spot the quantum machine</PhoneButton>
        </div>
      </PhoneScreen>
    )
  }

  const last = played - 1
  return (
    <PhoneScreen id="beat-round" title={`Beat the attacker: ${PHONE_NAME[machine].toLowerCase()}`}>
      <p className="phone-step">
        Round <span className="num">{played + 1}</span> of <span className="num">{BEAT_ROUNDS}</span>
      </p>
      <p className="phone-lead">What will the next bit be?</p>
      <div className="beat-keys">
        <PhoneButton variant="big" source={machine} onClick={() => guess(0)} label="Guess 0">
          0
        </PhoneButton>
        <PhoneButton variant="big" source={machine} onClick={() => guess(1)} label="Guess 1">
          1
        </PhoneButton>
      </div>
      <div className="beat-feedback" aria-live="polite">
        {played > 0 && (
          <>
            <p className="beat-feedback__bit">
              The bit was <span className={`num is-${machine}`}>{truths[last]}</span>.
            </p>
            <p>
              You guessed <span className="num">{guesses[last]}</span>:{' '}
              <strong>{guesses[last] === truths[last] ? 'right' : 'wrong'}</strong>.
            </p>
            <p>
              The attacker guessed <span className="num">{predictions[last]}</span>:{' '}
              <strong>{predictions[last] === truths[last] ? 'right' : 'wrong'}</strong>.
            </p>
            <p className="phone-small">
              So far: you <span className="num">{yours}</span>, the attacker <span className="num">{attackers}</span>, out
              of <span className="num">{played}</span>.
            </p>
          </>
        )}
      </div>
    </PhoneScreen>
  )
}
