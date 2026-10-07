import { useState } from 'react'
import { pools } from '../data/demo'
import type { Source } from '../data/types'
import { usePanelKeys } from '../deck/usePanelKeys'
import { count, percent } from '../lib/format'
import { GUESS_ROUNDS, readPool, randomStart } from '../lib/pool'
import { useSessionNumber } from '../lib/session'
import { countMatches } from '../lib/stats'
import { BitStream } from '../primitives/BitStream'
import { Num } from '../primitives/Num'
import { Panel } from '../primitives/Panel'
import { MACHINE_NAME } from './machines'
import { ActionButton, MachinePicker, type PanelBaseProps } from './shared'
import './panels.css'

/** Rounds shown in each history row (the most recent). */
const SHOWN_ROUNDS = 20

interface Rounds {
  /** Where in the pool this game's first round was. */
  from: number
  /** The room's guesses, in order. */
  guesses: number[]
}

interface GuessGamePanelProps extends PanelBaseProps {
  /** Machine to start on. */
  initialMachine?: Source
  /** Show what the attacker guessed each round, and its score. */
  showAttacker?: boolean
}

/**
 * "Guess the next bit" against one machine. The presenter presses 0 or 1 for the room's
 * guess; the true bit is revealed and the score updates. Each machine starts at a random
 * point in its pool, chosen once per session with room for at least GUESS_ROUNDS rounds,
 * and every round reads the next unread bit: the game never repeats or wraps the pool,
 * and stops at its end.
 */
export function GuessGamePanel({
  placement = 'inline',
  className,
  hideHeader,
  delay,
  keyboard = false,
  initialMachine = 'classical',
  showAttacker = false,
}: GuessGamePanelProps) {
  const [machine, setMachine] = useState<Source>(initialMachine)
  const [classicalCursor, setClassicalCursor] = useSessionNumber('guess:classical', () =>
    randomStart(pools.classical.length),
  )
  const [quantumCursor, setQuantumCursor] = useSessionNumber('guess:quantum', () => randomStart(pools.quantum.length))
  const cursor = machine === 'classical' ? classicalCursor : quantumCursor
  const setCursor = machine === 'classical' ? setClassicalCursor : setQuantumCursor

  // This panel's own games, one per machine; the cursor itself is shared by the session.
  const [games, setGames] = useState<Partial<Record<Source, Rounds>>>({})
  const game = games[machine]
  const rounds = game !== undefined && game.from + game.guesses.length === cursor ? game : { from: cursor, guesses: [] }

  const pool = pools[machine]
  const ended = cursor >= pool.length

  const guess = (bit: 0 | 1) => {
    if (ended) {
      return
    }
    readPool(pool, cursor, 1) // bounded: throws rather than wrap
    setGames((g) => ({ ...g, [machine]: { from: rounds.from, guesses: [...rounds.guesses, bit] } }))
    setCursor(cursor + 1)
  }
  const newGame = () => setGames((g) => ({ ...g, [machine]: { from: cursor, guesses: [] } }))

  usePanelKeys(
    {
      '0': () => guess(0),
      '1': () => guess(1),
      m: () => setMachine(machine === 'classical' ? 'quantum' : 'classical'),
    },
    keyboard,
  )

  const played = rounds.guesses.length
  const { bits: truths, predictions: attackerGuesses } = readPool(pool, rounds.from, played)
  const roomScore = countMatches(rounds.guesses, truths, played)
  const attackerScore = countMatches(attackerGuesses, truths, played)
  const lastTruth = played > 0 ? truths[played - 1] : undefined
  const lastRight = played > 0 ? rounds.guesses[played - 1] === lastTruth : undefined

  const recentFrom = Math.max(0, played - SHOWN_ROUNDS)
  const recentTruths = Array.from(truths.subarray(recentFrom))
  const recentGuesses = rounds.guesses.slice(recentFrom)
  const recentAttacker = Array.from(attackerGuesses.subarray(recentFrom))

  return (
    <Panel
      placement={placement}
      className={className}
      hideHeader={hideHeader}
      delay={delay}
      title={`Guess the next bit: ${MACHINE_NAME[machine].toLowerCase()}`}
      description={
        <>
          {placement === 'standalone' ? 'Tap' : 'Call out'} 0 or 1. Each round shows a bit the machine really made, one the attacker never saw. The game starts at
          a random point and has room for at least <Num>{count(GUESS_ROUNDS)}</Num> rounds.
        </>
      }
      controls={
        <div className="panel-row">
          <MachinePicker value={machine} onChange={setMachine} />
          <ActionButton onClick={newGame} disabled={played === 0}>
            New game
          </ActionButton>
        </div>
      }
    >
      <div className={`guess${showAttacker ? ' guess--attacker' : ''}`}>
        <div className="guess__play">
          <div className="guess__keys">
            <ActionButton variant="big" source={machine} onClick={() => guess(0)} disabled={ended} label="Guess 0">
              0
            </ActionButton>
            <ActionButton variant="big" source={machine} onClick={() => guess(1)} disabled={ended} label="Guess 1">
              1
            </ActionButton>
          </div>
          <div className="guess__result" aria-live="polite">
            {ended ? (
              <p className="guess__verdict">End of the recorded bits.</p>
            ) : lastTruth === undefined ? (
              <p className="guess__verdict is-muted">Round 1: what will the next bit be?</p>
            ) : (
              <>
                <p key={played} className={`guess__bit num reveal is-${machine}`}>
                  {lastTruth}
                </p>
                <p className="guess__verdict">
                  Round <Num>{played}</Num>: the bit was <Num>{lastTruth}</Num>. The room was {lastRight ? 'right' : 'wrong'}.
                </p>
              </>
            )}
          </div>
        </div>

        <div className="guess__history">
          <div className="guess__scores">
            <Score who="The room" right={roomScore} played={played} source={machine} />
            {showAttacker && <Score who="The attacker" right={attackerScore} played={played} source={machine} />}
          </div>
          {played > 0 && (
            <dl className="guess__rows">
              <HistoryRow name="The bits" source={machine} bits={recentTruths} />
              <HistoryRow name="Room guessed" source={machine} bits={recentGuesses} truths={recentTruths} />
              {showAttacker && (
                <HistoryRow name="Attacker guessed" source={machine} bits={recentAttacker} truths={recentTruths} />
              )}
            </dl>
          )}
          {played > 0 && (
            <p className="term">
              The last <Num>{recentTruths.length}</Num> rounds. A bar under a guess means it was right; grey guesses were
              wrong.
            </p>
          )}
        </div>
      </div>
    </Panel>
  )
}

function Score({ who, right, played, source }: { who: string; right: number; played: number; source: Source }) {
  return (
    <p className="guess__score">
      <span className="guess__who">{who}</span>{' '}
      <span className={`num is-${source}`}>
        {count(right)} of {count(played)}
      </span>
      {played > 0 && <span className="num is-muted"> ({percent(right / played, 0)})</span>}
    </p>
  )
}

function HistoryRow({
  name,
  source,
  bits,
  truths,
}: {
  name: string
  source: Source
  bits: readonly number[]
  truths?: readonly number[]
}) {
  return (
    <div className="guess__row">
      <dt>{name}</dt>
      <dd>
        <BitStream
          source={source}
          bits={bits}
          predictions={truths}
          perRow={SHOWN_ROUNDS}
          duration={0}
          label={truths === undefined ? `${name}: the true bits` : `${name}; a bar marks each right guess`}
        />
      </dd>
    </div>
  )
}
