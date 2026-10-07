import { useState } from 'react'
import { demo } from '../data/demo'
import { useSessionNumber } from '../lib/session'
import { Bitmap } from '../primitives/Bitmap'
import { PHONE_NAME, type Screen } from './names'
import { PhoneButton, PhoneScreen } from './parts'
import { SPOT_PAIRS, SPOT_ROUNDS, spotPair, type SpotImage } from './spotDeck'

interface Game {
  /** First pair of this game, in the session's order. */
  first: number
  rounds: number
  /** The player's answer for each round so far: true if they picked the quantum image. */
  answers: boolean[]
}

/**
 * "Spot the quantum machine": five rounds, each a fresh pair of unlabelled images, one
 * from each machine, in random left/right order. Tap the one you think is quantum; the
 * reveal names both. No image is shown twice in a session.
 */
export function SpotGame({ go }: { go: (screen: Screen) => void }) {
  const [next, setNext] = useSessionNumber('spot:next', () => 0)
  const [game, setGame] = useState<Game | null>(null)

  const start = () => {
    const rounds = Math.min(SPOT_ROUNDS, SPOT_PAIRS - next)
    if (rounds <= 0) {
      return
    }
    setGame({ first: next, rounds, answers: [] })
    setNext(next + rounds)
  }

  if (game === null) {
    const left = SPOT_PAIRS - next
    return (
      <PhoneScreen id="spot-start" title="Spot the quantum machine">
        <p className="phone-lead">
          Each round shows two pictures of random bits, one square per bit. One came from the quantum computer. Which?
        </p>
        {left > 0 ? (
          <PhoneButton variant="primary" onClick={start}>
            Start
          </PhoneButton>
        ) : (
          <p className="phone-lead" role="status">
            You have seen every recorded picture. Try the other game.
          </p>
        )}
        <div className="phone-actions">
          <PhoneButton onClick={() => go('beat')}>Beat the attacker instead</PhoneButton>
        </div>
      </PhoneScreen>
    )
  }

  const answered = game.answers.length
  const done = answered === game.rounds
  const score = game.answers.filter(Boolean).length

  if (done) {
    return (
      <PhoneScreen id="spot-end" title="Spot the quantum machine">
        <p className="phone-score" role="status">
          You spotted it <span className="num">{score}</span> of <span className="num">{game.rounds}</span> times.
        </p>
        <p className="phone-lead">Hard to tell apart by eye. {demo.copy.shannon_comparison}</p>
        <div className="phone-actions">
          {SPOT_PAIRS - next > 0 && (
            <PhoneButton onClick={start}>Play again with new pictures</PhoneButton>
          )}
          <PhoneButton variant="primary" onClick={() => go('beat')}>
            Next game: Beat the attacker
          </PhoneButton>
          <PhoneButton onClick={() => go('end')}>What it all means</PhoneButton>
        </div>
      </PhoneScreen>
    )
  }

  // The round being played; it records its answer when the player moves on.
  const pair = spotPair(game.first + answered)
  const images: SpotImage[] = pair.quantumLeft ? [pair.quantum, pair.classical] : [pair.classical, pair.quantum]
  return (
    <SpotRound
      key={game.first + answered}
      round={answered}
      rounds={game.rounds}
      images={images}
      onAnswer={(right) => setGame({ ...game, answers: [...game.answers, right] })}
    />
  )
}

function SpotRound({
  round,
  rounds,
  images,
  onAnswer,
}: {
  round: number
  rounds: number
  images: SpotImage[]
  onAnswer: (pickedQuantum: boolean) => void
}) {
  const [picked, setPicked] = useState<number | null>(null)
  const revealed = picked !== null
  const right = revealed && images[picked].source === 'quantum'
  return (
    <PhoneScreen id="spot-round" title="Which came from the quantum computer?">
      <p className="phone-step">
        Round <span className="num">{round + 1}</span> of <span className="num">{rounds}</span>
      </p>
      <div className="spot-pair">
        {images.map((image, i) => (
          <figure key={image.source} className="spot-pair__item" data-spot={`${image.source}:${image.startBit}`}>
            <button
              type="button"
              className={`spot-pair__choice${picked === i ? ' is-picked' : ''}`}
              onClick={() => setPicked(i)}
              disabled={revealed}
              aria-label={`Picture ${'AB'[i]}`}
            >
              <Bitmap
                source={image.source}
                tone={revealed ? 'source' : 'neutral'}
                bitmap={{ size: image.size, bits: image.bits, filled: image.size * image.size }}
                label={revealed ? `${PHONE_NAME[image.source]}: ${image.size} by ${image.size} bits` : `Picture ${'AB'[i]}`}
              />
            </button>
            <figcaption className="spot-pair__caption">
              {revealed ? <span className={`is-${image.source}`}>{PHONE_NAME[image.source]}</span> : <>Picture {'AB'[i]}</>}
            </figcaption>
          </figure>
        ))}
      </div>
      {revealed ? (
        <div className="phone-feedback" role="status">
          <p className="phone-score">{right ? 'Right!' : 'Not this time.'}</p>
          <PhoneButton variant="primary" onClick={() => onAnswer(right)}>
            {round + 1 < rounds ? 'Next pair' : 'See your score'}
          </PhoneButton>
        </div>
      ) : (
        <p className="phone-lead">Tap the picture you think came from the quantum computer.</p>
      )}
    </PhoneScreen>
  )
}
