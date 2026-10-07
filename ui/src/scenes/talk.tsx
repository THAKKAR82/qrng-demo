// The talk: nine slides in order (SPEC.md, Section 9.4). Every number and comparative
// phrase on a slide or in the notes comes from demo.json; copy is plain English, with
// technical terms only in small secondary text.

import { demo, isSynthetic } from '../data/demo'
import type { SceneDef } from '../deck/types'
import { audienceUrl } from '../lib/audienceUrl'
import { CrossCheckNotes, PhoneInvite, RunNote } from './parts'
import { count, fixed, percent, percentRange, utcDate } from '../lib/format'
import { revealDelay } from '../lib/motion'
import { AttackerPanel } from '../panels/AttackerPanel'
import { GuessGamePanel } from '../panels/GuessGamePanel'
import { HardwarePanel } from '../panels/HardwarePanel'
import { LiveNotes } from '../panels/LiveRun'
import { MachinesPanel } from '../panels/MachinesPanel'
import { TellApartPanel } from '../panels/TellApartPanel'
import { UnpredictabilityPanel } from '../panels/UnpredictabilityPanel'
import { Num } from '../primitives/Num'
import { Scene } from '../primitives/Scene'
import './talk.css'

const { metadata: meta, classical, quantum, copy } = demo
const url = audienceUrl()

export const talkScenes: readonly SceneDef[] = [
  {
    id: 'opening',
    title: 'Opening',
    notes: (
      <>
        <p>
          Welcome. One question for the next few minutes: can you predict a random bit? We'll compare two machines, one
          of them a real quantum computer.
        </p>
        {url === null ? (
          <p>No audience URL was set at build time (VITE_AUDIENCE_URL), so there is no QR code.</p>
        ) : (
          <p>
            Invite phones now: the QR code opens <Num>{url.short}</Num>. Phones get a separate copy of the app; nothing is
            connected.
          </p>
        )}
        <RunNote />
      </>
    ),
    render: () => (
      <section className="opening">
        <div className="opening__title">
          <h1 className="opening__headline reveal">Can you predict a random bit?</h1>
          {url !== null && (
            <p className="opening__lede reveal" style={revealDelay(100)}>
              Play along on your phone, or just raise your hand.
            </p>
          )}
        </div>
        <PhoneInvite heading="Play along" />
      </section>
    ),
  },
  {
    id: 'why',
    title: 'Why randomness matters',
    notes: (
      <>
        <p>
          Keep it concrete. Every example depends on the same thing: nobody can guess the next number, not even someone who
          has watched all the earlier ones.
        </p>
        <p>Ask: who here has used a password generator, a lottery, or shuffled a playlist?</p>
      </>
    ),
    render: () => (
      <Scene
        title="Random numbers quietly keep things fair and secret"
        lede="All of these rely on one thing: nobody can predict the next number."
      >
        <ul className="uses">
          {[
            ['Passwords and keys', 'The lock on your bank login is only as strong as the random number behind it.'],
            ['Draws and lotteries', 'A fair draw means no one could know the winner in advance.'],
            ['Games and shuffles', 'Card games and playlists feel fair because the next card is a surprise.'],
            ['Science and forecasts', 'Simulations of weather or medicine roll millions of dice.'],
          ].map(([name, text], i) => (
            <li key={name} className="uses__item reveal" style={revealDelay(150 + 100 * i)}>
              <h2 className="uses__name">{name}</h2>
              <p className="uses__text">{text}</p>
            </li>
          ))}
        </ul>
      </Scene>
    ),
  },
  {
    id: 'machines',
    title: 'Meet the two machines',
    notes: (
      <>
        <p>
          Press Generate bits. Left: Python's built-in random number generator, the one most programs reach for. Right: bits
          from measuring qubits on a real quantum computer. Both are playing back bits they really made; nothing is
          generated live here.
        </p>
        <p>
          Point at the numbers: both sit near half 1s, and the ordinary randomness score is close to 1 for both.
        </p>
        {__QRNG_LIVE__ && <LiveNotes />}
        <RunNote />
      </>
    ),
    render: () => (
      <Scene
        title="Meet the two machines"
        lede="Each square is one bit: coloured for 1, blank for 0. Both machines play back bits they really made."
      >
        <MachinesPanel className="talk__wide" hideHeader keyboard />
      </Scene>
    ),
  },
  {
    id: 'tell-apart',
    title: 'Can you tell them apart?',
    steps: 3,
    notes: (
      <>
        <p>
          Show of hands: who thinks picture A is the quantum machine? Who thinks B? Then press → (or R) to reveal, and →
          again for the ordinary statistics.
        </p>
        <p>
          {copy.shannon_comparison} Classical <Num>{fixed(classical.shannon_entropy.pooled, 5)}</Num>, quantum (average per
          qubit) <Num>{fixed(quantum.shannon_entropy.per_qubit_mean, 5)}</Num> bits per bit.
        </p>
        <p>Don't claim the quantum bits score higher: with readout bias they are usually a touch lower.</p>
      </>
    ),
    render: (step) => (
      <Scene
        title="Can you tell them apart?"
        lede={
          <>
            The first <Num>{count(classical.bitmap.size ** 2)}</Num> bits from each machine, both drawn in black so colour
            gives nothing away.
          </>
        }
      >
        <TellApartPanel className="talk__wide" hideHeader keyboard revealed={step >= 1} showGauges={step >= 2} />
      </Scene>
    ),
  },
  {
    id: 'guess',
    title: 'Guess the next bit',
    notes: (
      <>
        <p>
          Let the room call out 0 or 1; press 0 or 1 for the majority. M switches machines. Expect the room to hover
          around half right on both: people can't predict either one.
        </p>
        <p>Each machine starts at a random point in bits the attacker never saw, and never repeats a bit.</p>
      </>
    ),
    render: () => (
      <Scene
        title="Guess the next bit"
        lede="Call out 0 or 1. Every bit is one the machine really made, and one the attacker never saw."
      >
        <GuessGamePanel className="talk__wide" hideHeader keyboard />
      </Scene>
    ),
  },
  {
    id: 'attacker',
    title: 'Enter the attacker',
    steps: 2,
    notes: (
      <>
        <p>
          Step 1: play a few rounds with the attacker row on, on both machines (M switches), and compare its score with the
          room's. Over all the unseen bits: {copy.classical_attack} {copy.quantum_attack}
        </p>
        <p>
          Step 2: launch the attacker on each machine. On the classical machine it scored{' '}
          <Num>{percent(classical.attacker.accuracy, 2)}</Num> after watching{' '}
          <Num>{count(classical.attacker.n_training_bits)}</Num> bits; on the quantum machine,{' '}
          <Num>{percent(quantum.attacker.accuracy, 2)}</Num> (95% <Num>{percentRange(quantum.attacker.ci_low, quantum.attacker.ci_high, 2)}</Num>).
        </p>
        <p>
          Why: the classical generator has a hidden state that its output gives away. A qubit has no hidden state to steal;
          the best an attacker can do is learn which way each qubit leans.
        </p>
        <CrossCheckNotes />
      </>
    ),
    render: (step) => (
      <Scene
        title="Enter the attacker"
        lede={
          step === 0
            ? 'Same game, but now an attacker that has studied each machine guesses too.'
            : 'The attacker watches a machine, then predicts bits it has never seen.'
        }
      >
        {step === 0 ? (
          <GuessGamePanel className="talk__wide" hideHeader keyboard showAttacker />
        ) : (
          <AttackerPanel className="talk__wide" hideHeader keyboard chartWidth={1040} chartHeight={460} />
        )}
      </Scene>
    ),
  },
  {
    id: 'unpredictability',
    title: 'Measuring unpredictability',
    notes: (
      <>
        <p>
          {copy.unpredictability_comparison} Classical <Num>{fixed(classical.attacker.min_entropy, 3)}</Num> bits, quantum{' '}
          <Num>{fixed(quantum.attacker.min_entropy, 3)}</Num> bits (conservative{' '}
          <Num>{fixed(quantum.attacker.min_entropy_conservative, 3)}</Num>).
        </p>
        <p>
          This is measured against these attackers. It is not a certified, device-independent bound; a cleverer attacker
          might exploit drift or correlations. The notebook checks one such attacker.
        </p>
      </>
    ),
    render: () => (
      <Scene
        title="Measuring unpredictability"
        lede="How many bits of genuine surprise each bit contains, for someone trying to predict it."
      >
        <UnpredictabilityPanel className="talk__wide" hideHeader />
      </Scene>
    ),
  },
  {
    id: 'play',
    title: 'Your turn: play on your phone',
    notes: (
      <>
        <p>
          Give people a couple of minutes. The phone version has two games: Spot the quantum machine (five pairs of
          pictures) and Beat the attacker (twenty guesses against an attacker on either machine).
        </p>
        {url === null ? (
          <p>No audience URL was set at build time (VITE_AUDIENCE_URL), so there is no QR code on this slide.</p>
        ) : (
          <p>
            The QR code opens <Num>{url.short}</Num>. Phones get a separate copy of the app; nothing is connected. Press Q at
            any point in the talk to show the code again.
          </p>
        )}
      </>
    ),
    render: () => (
      <Scene
        title="Your turn: play on your phone"
        lede="Two quick games: spot the quantum machine, then try to beat the attacker."
      >
        <PhoneInvite heading="Scan to play" large />
      </Scene>
    ),
  },
  {
    id: 'takeaway',
    title: 'Takeaway',
    notes: (
      <>
        <p>
          Honest caveat: good classical generators are also unpredictable in practice. The operating system's secure
          generator (for example os.urandom) can't be predicted by any known practical attack; its guarantee rests on
          computational hardness, while the quantum guarantee rests on physics. We used Python's default random module
          because it is what many programs reach for, not because it is the best classical option.
        </p>
        <CrossCheckNotes />
        <RunNote />
      </>
    ),
    render: () => (
      <Scene title="Takeaway">
        <ol className="takeaway">
          <li className="takeaway__item reveal" style={revealDelay(100)}>
            <h2 className="takeaway__point">Quantum computers are real.</h2>
            <p className="takeaway__text">
              {isSynthetic || meta.backend === null ? (
                <>This copy of the demo shows sample data, not quantum hardware output.</>
              ) : (
                <>
                  These bits came from IBM Quantum <Num>{meta.backend}</Num>
                  {meta.date_utc !== null && <> on {utcDate(meta.date_utc)}</>}.
                </>
              )}
            </p>
          </li>
          <li className="takeaway__item reveal" style={revealDelay(250)}>
            <h2 className="takeaway__point">They are accessible today.</h2>
            <p className="takeaway__text">Anyone can send a small job like this one over the internet to a real chip.</p>
          </li>
          <li className="takeaway__item reveal" style={revealDelay(400)}>
            <h2 className="takeaway__point">Their randomness is guaranteed by physics.</h2>
            <p className="takeaway__text">
              {copy.unpredictability_comparison} No hidden state decides a qubit's outcome, so there is nothing for an
              attacker to steal.
            </p>
          </li>
        </ol>
      </Scene>
    ),
  },
  {
    id: 'inside',
    title: 'Inside the quantum computer',
    notes: (
      <>
        <p>
          Appendix, for questions. The map shows the chip's qubits; the coloured ones were used in this run. Click a qubit
          to show how often it read 1, how often it misreads, and how far it sits from half.
        </p>
        <p>
          {copy.bias_note} Flagged qubits: <Num>{count(quantum.bias_tests.flagged_columns.length)}</Num> (their share of 1s
          sits more than <Num>{fixed(quantum.bias_tests.z_threshold, 0)}</Num> standard errors from half). They were kept,
          not removed: every bit they produced is in the data and in every result, and no bias correction was applied.
        </p>
      </>
    ),
    render: () => (
      <Scene
        title="Inside the quantum computer"
        lede={
          <>
            The <Num>{count(quantum.qubits.length)}</Num> qubits used are coloured: deeper means further from reading 0 and
            1 equally often. Ringed qubits were flagged, and kept.
          </>
        }
      >
        <HardwarePanel className="talk__wide" hideHeader />
      </Scene>
    ),
  },
]
