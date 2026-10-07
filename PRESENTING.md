# Presenting

Everything for the day of the talk: the checklist, a slide-by-slide walkthrough, what to do when something fails, and the clean-up afterwards. Setup is in README.md; hosting the phone site is in DEPLOY.md.

**The presenter notes (N) appear on the projected screen**, over the slide, for everyone to see. Read them while rehearsing, and keep this document printed or on your phone during the talk. The exact numbers to quote are in the notes for each slide; this document doesn't repeat them, so they always match the data being shown.

## Days before

- **Collect at least a day before the talk**, if you want a fresh run: `python -m pipeline.tasks refresh` on one Mac, then commit `data/runs/<run_id>/`, `ui/src/data/demo.json`, and `demo/index.html`, and push (README, "Syncing the two Macs"). A day's margin covers a busy queue, a failed job, or a recovery with `--from-job`. The committed run is perfectly good if you don't.
- **Rehearse at home.** `npm run preview -- --host` (README, "Phones and the QR code") lets phones on your Wi-Fi play against the laptop. It also serves the **whole presenter build, notes included, to everyone on the same network**, so use it only on a trusted home network for rehearsals, **never at the venue**. At the talk, phones use the hosted site only.

## Before the talk (on the presenting Mac)

1. **Pull:** `git pull`.
2. **Rebuild with the hosted address:** `source .venv/bin/activate && python -m pipeline.tasks rebuild`. Check that it prints the hosted address from `site.json` (not the placeholder warning) and ends with every build checked. If `git diff` shows only the export time in `demo.json` and `demo/index.html`, discard it: `git checkout ui/src/data/demo.json demo/index.html`.
3. **Deploy the phone site** (DEPLOY.md, step 4), unless the live copy is already this build.
4. **Check it:** `python -m pipeline.tasks check-site`. Every line must say `ok`.
5. **Start the deck.** Either:
   - **without the live run:** `cd ui && npm run serve` and open the address it prints (`http://localhost:4173/`). Don't use `npm run preview` here: it rebuilds without the hosted address and the QR code disappears;
   - **with the live run** (optional): `python -m pipeline.tasks live-server`. Check the address it says the build points to, type the backend name to arm it, and open `http://127.0.0.1:8765/`. Arm it shortly before the talk: each live run uses a little of the shared free allowance, at most three per session.
6. Press **F** for fullscreen. Make sure the laptop's display settings won't sleep or show notifications on the projector (Do Not Disturb on).
7. **Scan the QR code on slide 1 with your own phone, on the venue's network** (guest Wi-Fi and mobile data both). It should open the games and say "Can you beat a quantum computer?". If it doesn't, see the fallbacks.
8. **Test the clicker:** next, back, and back again across a slide with steps (slide 4 or 6). Press Home to return to slide 1.
9. Keep `demo/index.html` on the laptop (it's in the repo) as the offline fallback.

## Keys

| Key | Does |
|---|---|
| → ↓ PageDown Space (clicker "next") | Next step, then next slide |
| ← ↑ PageUp (clicker "back") | Back |
| Home / End | First / last slide |
| F | Fullscreen |
| Q | Large QR code over any slide; Q again or Escape closes it |
| N | Presenter notes, shown on screen |
| 0 / 1 | The room's guess (slides 5 and 6) |
| R | Reveal the pictures (slide 4) |
| M | Switch machine (slides 5 and 6) |

## Slide by slide

**1. Can you predict a random bit?** (opening; QR code and short address)
- Welcome. One question for the next few minutes: can you predict a random bit? Two machines, one of them a real quantum computer.
- **Ask:** "Hands up if you think a computer can make a truly random number."
- Invite phones: "Scan the code to play along, or just raise your hand." Phones get their own copy of the games; nothing connects them to this screen.

**2. Random numbers quietly keep things fair and secret**
- Keep it concrete: passwords and keys, draws and lotteries, games and shuffles, simulations. All rely on one thing: nobody can guess the next number, not even someone who has watched all the earlier ones.
- **Ask:** "Hands up if you've used a password generator, bought a lottery ticket, or shuffled a playlist this week."

**3. Meet the two machines**
- Press **Generate bits** (Fast if time is short). Left: Python's built-in random number generator, the one most programs reach for. Right: bits from measuring qubits on a real quantum computer, labelled with the machine's size, such as "Run on a 156-qubit IBM quantum computer" (the size comes from the run's data). Both play back bits they really made.
- Point at the numbers: both sit near half 1s, and the ordinary randomness score is close to 1 for both.
- **With the live run:** press "Run on real quantum hardware now". The slide shows each stage (sending, waiting in IBM's queue, running), then streams the fresh bits. Live numbers are small and noisy; quote the headline numbers from the full run. If it falls back after two minutes or fails, say "IBM's queue is busy right now; here's the run we recorded earlier" and carry on. The job may still finish; the server saves it.
- **"How do we know it really ran?"** The backend name and job ID are in the notes (N), not on screen; read them out, or press N to show them. The job ID is IBM's own record, visible in the IBM Quantum dashboard of the account that ran it, and the notebook shows every bit. During a live run the notes show the live job's ID as soon as it exists.

**4. Can you tell them apart?** (three steps)
- Two unlabelled pictures, both in black. **Ask:** "Hands up if you think picture A is the quantum one. Now B."
- **Next** (or R) reveals which is which. **Next** again shows the ordinary statistics: by these measures both look equally random.
- Don't claim the quantum bits score higher: with readout bias they are usually a touch lower. The point is that ordinary statistics can't tell them apart.

**5. Guess the next bit**
- **Say:** "Everyone shout 0 or 1!" Press **0** or **1** for whichever was louder; the slide reveals the true bit and keeps score. A few rounds, then **M** to switch machines and a few more.
- Expect the room to hover around half right on both: people can't predict either one.

**6. Enter the attacker** (two steps)
- Same game with an attacker row: everyone shouts 0 or 1 again, and the attacker guesses too. On the classical machine it should get every bit right; on the quantum machine, about as well as the room. The notes give its measured score over all the unseen bits.
- **Next** brings in the attacker panel. Press **Launch** on the classical machine: it watches 624 numbers, rebuilds the generator's hidden state, and predicts everything after. **M**, then **Launch** on the quantum machine: it learns which way each qubit leans, and the slide says in words how close to a coin flip it came.
- Why: the classical generator has a hidden state its output gives away. A qubit has no hidden state to steal.
- If asked whether the attackers were rigged: the notes have the cross-checks (each attacker run on the other machine scores about 50%).

**7. Measuring unpredictability**
- The headline: bits of genuine surprise per bit, for someone trying to predict it, from 0 (fully predictable) to 1 (a coin flip). Read the two numbers off the slide; the notes have the conservative value too.
- Caveat, if the audience is technical: this is measured against these attackers, not a certified bound against every possible one.

**8. Your turn: play on your phone**
- **Say:** "Phones out, scan the code." Give people two or three minutes. Two games: Spot the quantum machine (five pairs of pictures) and Beat the attacker (a short run of guesses; the notes give the number). On phones the classical machine is called the "ordinary formula".
- The Beat the attacker end screen tells players that a short game swings a lot by luck (the notes give the range most pure-guess games land in), so one game isn't the measurement; the full dataset is.
- Press **Q** now or later to show the code again for latecomers.

**9. Takeaway**
- Quantum computers are real (the slide names the machine by its size and gives the date), they are accessible today, and their randomness is guaranteed by physics.
- **The honest caveat:** good classical generators, such as the operating system's secure one, are unpredictable in practice too; their guarantee rests on computational hardness, the quantum one on physics. We used Python's default because many programs reach for it, not because it's the best classical option.

**10. Inside the quantum computer** (appendix, for questions)
- The chip's qubits; the coloured ones were used, deeper colour means further from reading 0 and 1 equally. Click a qubit for how often it read 1, how often it misreads, and how far it sits from half.
- Ringed qubits were flagged as biased. They were kept, not removed, and no bias correction was applied.

**When to press Q:** on slide 1 if people are still arriving, any time someone asks for the address, and during questions. Slide 8 already shows the code large.

## If something goes wrong

| Problem | What to do |
|---|---|
| **IBM is slow or the live run fails** | Nothing. The slide falls back to the recorded run by itself after two minutes, or as soon as it fails, and says so. Carry on; the talk never depends on the live run. |
| **The venue network is down** | Run the deck from `demo/index.html`: double-click it in Finder (it works with no network at all) and press F. Skip the QR code and slide 8's phone games ("the phone games need the internet; here's what they look like"), or play the games on the projector with `?view=audience`. |
| **Phones can't load the site** | Carry on. The talk doesn't depend on phones: the room plays along by raising hands and shouting guesses, and slide 8 can be short. |
| **The QR code is missing** | The build has no audience address (`rebuild` printed the placeholder warning, or `npm run preview` rebuilt without it). Read the short address aloud, or rebuild and serve with `npm run serve`. |
| **The deck shows "SYNTHETIC DATA"** | The build is using sample data, not the real run. Say so out loud, or rebuild after pulling the committed run. |
| **The clicker stops moving slides** | Click once on an empty part of the slide (not a button), then try again. |

## After the talk

1. **Take the phone site down** the same day (DEPLOY.md, "Taking the site down").
2. If you used the live run, stop the server with Ctrl-C. It lists any job that hadn't finished; finished live runs are in `data/live/` on this laptop (never committed).
3. Close the presenter tab: nothing else is running unless you started `npm run serve` or `live-server`.
