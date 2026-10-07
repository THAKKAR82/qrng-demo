# qrng-demo

A short live demo showing that quantum computers are usable today, and that quantum random bits are unpredictable in a way Python's default random number generator is not. SPEC.md explains the claim, the metric, and the honesty rules.

| Document | For |
|---|---|
| `README.md` | Setting up a Mac and everyday work (this file) |
| `PRESENTING.md` | The day of the talk: checklist, slide-by-slide walkthrough, fallbacks |
| `DEPLOY.md` | Hosting the phone site, checking it, and taking it down |
| `SPEC.md` | What the project must do; the source of truth |

## Layout

| Path | What |
|---|---|
| `pipeline/` | Python package: collection, analysis, task runner |
| `notebooks/` | The end-to-end analysis notebook |
| `ui/` | Presentation web app (Vite + React + TypeScript) |
| `data/runs/` | Committed real hardware runs, one folder per run |
| `data/sample/` | Committed **synthetic** placeholder data |
| `data/scratch/` | Local only (gitignored) |
| `demo/` | Committed single-file build of the UI |
| `site.json` | The hosted phone site's address (DEPLOY.md) |
| `scratch/` | Local only (gitignored) |

## Setup on macOS

Run the same steps on both Macs. You need Python 3.11 or newer (both Macs use 3.13) and Node 24 or newer (both Macs use the version in `.nvmrc`, currently 26.3.0).

**Keep the clone outside iCloud Drive and OneDrive.** Syncing services rewrite files inside `.venv` and `node_modules` behind your back (and can set the hidden flag that breaks the editable install; see Troubleshooting). On macOS, Desktop and Documents are often synced to iCloud, so use a folder such as `~/code/`.

```sh
cd ~/code
git clone <private-repo-url> qrng-demo
cd qrng-demo

python3.13 --version                 # must print 3.13.x; see Troubleshooting if not found
python3.13 -m venv .venv             # not bare python3: on macOS that is Apple's 3.9
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

(cd ui && npm ci)

pre-commit install
python -m pipeline.tasks setup-check
```

`python3.13` can come from python.org, Homebrew, or Anaconda; any of them is fine, as long as the venv is created with it explicitly.

`setup-check` prints Python, Node, and package versions and flags anything missing or different from the pins. It also catches the usual macOS setup problems (see Troubleshooting). It does not touch IBM credentials. If both Macs report `OK`, they are in sync.

## Everyday commands

```sh
source .venv/bin/activate
python -m pipeline.tasks setup-check     # versions and environment only
python -m pytest                         # tests (never contact IBM Quantum)
python -m ruff check . && python -m ruff format --check .   # lint
python -m mypy                           # type check
(cd ui && npm run lint && npm run typecheck)
pre-commit run --all-files               # secret scan, ruff, mypy, hygiene
python -m pipeline.tasks rebuild         # demo.json, notebook, and every UI build (no QPU time)
python -m pipeline.tasks ui-dev          # UI dev server
```

Running the tools as `python -m …` makes sure they come from `.venv`, even if another environment is on your PATH.

### Tasks

Everything runs through `python -m pipeline.tasks <task>` (SPEC.md, Section 10):

| Task | What it does | Who |
|---|---|---|
| `setup-check` | Versions and environment problems | Anyone |
| `export` | Writes `ui/src/data/demo.json` from the latest committed run | Anyone |
| `notebook` | Executes the notebook into `data/scratch/` | Anyone |
| `ui-build` | Builds the single-file `demo/index.html` | Anyone |
| `rebuild` | `export`, `notebook`, then `npm run build`, `build:demo`, and `build:web`, with the URL from `site.json` as `VITE_AUDIENCE_URL`. No QPU time. `--audience-url <url>` overrides `site.json` for a rehearsal | Anyone |
| `check-site` | Checks the deployed phone site (DEPLOY.md); contacts only that site | **You only** |
| `collect-quantum` | Real hardware collection (below); `--dry-run` is offline | **You only** |
| `refresh` | `collect-quantum` with all its confirmations, then `rebuild` | **You only** |
| `live-server` | The optional live run on slide 3 (below) | **You only** |

### Syncing the two Macs

Both Macs share one GitHub repo and one IBM account. A real run is collected once, on one Mac, and travels through git:

1. **On the Mac that collects** (at least a day before the talk, so there is time to recover from a busy queue or a failed job): `python -m pipeline.tasks refresh`. It collects, exports, re-runs the notebook, and rebuilds.
2. Commit the new `data/runs/<run_id>/` folder, `ui/src/data/demo.json`, and `demo/index.html`, then push.
3. **On the other Mac:** `git pull`, then `python -m pipeline.tasks rebuild`. The builds match the first Mac's, because they come from the same committed run and the same `site.json`. The only difference `git diff` should show is the export time (`generated_utc`) in `demo.json` and `demo/index.html`; discard it with `git checkout ui/src/data/demo.json demo/index.html`.

Never collect on both Macs for the same talk: the free allowance is shared (below). Builds in `ui/dist/` and `ui/dist-web/` are not committed; each Mac makes its own with `rebuild`.

## The web app

The app in `ui/` has two parts (SPEC.md, Section 9): the **presenter view**, a slide deck for the projector, and the **phone version**, two short games for the audience. Use the Node version in `.nvmrc` (`nvm use`).

| Command | Use it for |
|---|---|
| `cd ui && npm run dev` | Working on the UI. Same as `python -m pipeline.tasks ui-dev`. |
| `cd ui && npm run preview` | Builds into `ui/dist/` and serves it on this laptop at the URL it prints. It rebuilds with whatever `VITE_AUDIENCE_URL` is in your shell, which is usually none. |
| `cd ui && npm run serve` | **Presenting.** Serves the last build in `ui/dist/` without rebuilding, so the QR code `rebuild` baked in is kept. |
| `cd ui && npm run build:demo` | The fallback: one self-contained `demo/index.html` that opens by double-click, offline. Same as `python -m pipeline.tasks ui-build`. |
| `cd ui && npm run build:web` | **The phone site.** Only the phone version, in `ui/dist-web/`, with `index.html` at the root and the host's `_headers` file. DEPLOY.md uploads it. `npm run preview:web` serves it locally. |
| `python -m pipeline.tasks live-server` | **Optional: presenting with a live IBM run on slide 3.** Serves the last `npm run build` from `ui/dist/` on this laptop only. Human only; see [Live run on slide 3](#live-run-on-slide-3). |

The presenter view opens on slide 1 of the ten-slide talk (SPEC.md, Section 9.4; slide 10 is an appendix for questions). Some slides have steps: "next" first reveals the next part of the slide. Every slide has presenter notes. PRESENTING.md walks through them.

Keys in the presenter view: → / ↓ / PageDown / Space next, ← / ↑ / PageUp back, Home and End, N presenter notes, F fullscreen, P the primitives page, Q a large QR code for phones (Q again or Escape closes it). Clickers that send PageUp and PageDown work as-is. On the interactive slides: 0 and 1 enter the room's guess, R reveals the pictures, and M switches between the classical and quantum machines. Add `#primitives` (or `?primitives`) to the URL to open the primitives page directly; it works under `file://` too.

### Phones and the QR code

The phone version has an intro, two games (Spot the quantum machine; Beat the attacker), and a closing screen. It has no slides, notes, or presenter keys, and it is not connected to the presenter's laptop. In the presenter builds the same screens open with `?view=audience`.

The QR code (on slide 1, slide 8, and the Q overlay) shows `VITE_AUDIENCE_URL`, which is read **when you build**. It is drawn in the app; no online service is involved. With no setting, those places show no code.

**For the real talk**, the address is the hosted phone site's, from `site.json`, and `rebuild` builds everything with it. Choose the project name and deploy first; DEPLOY.md has the order.

**For a rehearsal at home**, point phones at the laptop. This serves the presenter build, **notes included**, to everyone on the same network, so do it only on a trusted home network, never at the venue (PRESENTING.md):

```sh
cd ui
VITE_AUDIENCE_URL="http://$(ipconfig getifaddr en0):4173/?view=audience" npm run preview -- --host
```

Every build uses whatever `ui/src/data/demo.json` holds; `rebuild` (or `export`) refreshes it. If the data is synthetic, a label saying so stays on every screen, phone screens included.

### Checking the UI

To check the UI visually (development only; downloads browsers once with `npx playwright install chromium firefox webkit`):

```sh
cd ui
npm run preview                                    # in one terminal
node scripts/verify.mjs --url http://localhost:4173/ --synthetic no
node scripts/verify.mjs --url http://localhost:4173/ --live-mock
npm run build:demo && node scripts/verify.mjs --file ../demo/index.html --synthetic no
npm run preview:web -- --port 4174                 # in another terminal
node scripts/verify.mjs --web http://localhost:4174/ --synthetic no
```

The verifier walks every slide and step and every primitive at 1920×1080 and 1280×720, drives each panel, checks slide 8 and the Q overlay, and plays both phone games at 390×844 and 375×560 with touch, including real touch scrolling. On every slide and phone screen it checks that text keeps at least 3:1 contrast on a washed-out projector (contrast reduced by 30%), and that the backend name and job ID are not on screen. With `--web` it checks only the phone site: that its files hold no presenter content, live-run code, or source maps, and that both games run with no CSP violation under the headers in `_headers`, in Chromium, Firefox, and WebKit. Add `--qr yes` when the build has a `VITE_AUDIENCE_URL`, or `--qr no` when it doesn't. Screenshots land in `data/scratch/ui-verify/`.

Every run also checks that the live-run control is absent: from plain preview, from `demo/index.html` (which holds no live code at all), and from the phone site. `--live-mock` checks the live run itself without IBM or the live server: the browser stands in for the live server and checks slide 3 when the server is unarmed, when it can't be reached, and when it is armed: a finished run, the two-minute timeout, a failed job, the server going away mid-run, and a refused start.

### Fonts

The UI uses IBM Plex Sans and IBM Plex Mono, self-hosted in `ui/src/fonts/` under the SIL Open Font License 1.1 (full text in `ui/src/fonts/LICENSE.txt`). The files are IBM's own split subsets from `@ibm/plex-sans` 1.1.0 and `@ibm/plex-mono` 2.5.0, unmodified. `ui/src/fonts/README.md` records the source URLs and SHA-256 hashes.

## IBM Quantum account

Credentials are not stored in this repo. Each Mac has the same Qiskit saved account, named `qrng-open`, in `~/.qiskit`, pinned to a free Open Plan instance. To use a different saved account name, set `QRNG_IBM_ACCOUNT`.

**Both machines share one free QPU allowance: 10 minutes per 28 days.** A default collection run uses a few seconds. Even so, run real collection deliberately, from one machine at a time, and commit the resulting run folder so the other machine doesn't need to collect again.

### Verify the saved account (run this yourself, not Claude)

This connects to IBM Quantum and lists real backends. It submits no jobs and uses no QPU time.

```sh
source .venv/bin/activate
python - <<'EOF'
from qiskit_ibm_runtime import QiskitRuntimeService

service = QiskitRuntimeService(name="qrng-open")
print("Backends:", [b.name for b in service.backends(simulator=False, operational=True)])

# Plan of the active instance (the collector refuses anything but "open").
active = service.active_instance()
plans = [(i["plan"], i.get("pricing_type")) for i in service.instances() if i["crn"] == active]
print("Plan, pricing type:", plans)
print("Usage:", {k: v for k, v in service.usage().items() if "seconds" in k})
EOF
```

Expect a list of backends such as `ibm_fez`, and `[('open', 'free')]` for the plan and pricing type. The script deliberately doesn't print the CRN. Don't paste its output anywhere public.

### Real collection

Only the human runs real collection, at least a day before the talk. It is interactive by design: it confirms the Open Plan (`plan` must be exactly `open` and `pricing_type` exactly `free`; if the API can't tell, you are asked to type `open plan`), checks the remaining allowance, shows a summary with a rough QPU-time estimate, and asks you to type the backend name before it submits anything. See SPEC.md, Section 6.3.

```sh
source .venv/bin/activate
python -m pipeline.tasks collect-quantum --dry-run   # offline: real Sampler on Aer with a fake backend
python -m pipeline.tasks refresh                     # real: collect-quantum, then rebuild
```

`refresh` takes the same options as `collect-quantum` (below). To collect without rebuilding, run `python -m pipeline.tasks collect-quantum` and then `rebuild` yourself.

If anything goes wrong after the job is submitted (you press Ctrl-C while it waits, the network drops, or writing fails), the collector prints a recovery command. Run it to write the run folder from the finished job without submitting anything new:

```sh
python -m pipeline.tasks collect-quantum --from-job <job_id>
```

This works best on the Mac that submitted the job, which keeps a submission record in `data/scratch/pending/`. On the other Mac, also pass `--physical-qubits` with the list from the submission summary.

Useful flags: `--shots N`, `--qubits N`, `--backend ibm_fez`, `--no-qubit-selection`, `--physical-qubits 3,7,12`. The run lands in `data/runs/<UTC time>_<backend>/` with `quantum.npz`, `quantum.json`, and the matching `classical.npz` and `classical.json`. Commit that folder (see [Syncing the two Macs](#syncing-the-two-macs)).

### Live run on slide 3

Optional, and only on the presenter's laptop: `live-server` serves the presenter app with a "Run on real quantum hardware now" button on slide 3. Pressing it runs one small job (10 qubits, 200 shots, 2,000 bits) on real hardware and streams the fresh bits into the quantum machine. If no result arrives within two minutes, or anything fails, the slide says so and keeps the recorded run. See SPEC.md, Section 6.4.

**Build first, with the hosted phone address.** `live-server` serves whatever is in `ui/dist/` and never rebuilds it, so the QR codes on slides 1 and 8 and the Q overlay come from your last build. For the real talk:

```sh
source .venv/bin/activate
python -m pipeline.tasks rebuild                  # builds ui/dist/ with site.json's address
python -m pipeline.tasks live-server              # or --backend ibm_fez, --port 8765
```

At startup it prints the `VITE_AUDIENCE_URL` baked into the build it is about to serve, or warns that none is set; rebuild if it isn't the address you expect. It then arms itself with the collector's checks: an interactive terminal, the Open Plan, and the remaining allowance, which must cover all three runs. It shows the backend, the 10 lowest-readout-error qubits, 200 shots, at most 3 live runs this session, and a 30 s execution limit per run, and you type the backend name to arm it. If you type anything else, or a check fails, it still serves the app, but without the live button. Open the address it prints (`http://127.0.0.1:8765/`) in the browser on the same laptop. It listens on 127.0.0.1 only, so phones and other machines can't reach it, and there is no option to change that.

The slide names the machine by its size ("Fresh from a 156-qubit IBM quantum computer"); the live job's ID and backend appear in the presenter notes (N) as soon as they exist. Finished live runs are saved to `data/live/` on that laptop. That folder is gitignored, never exported, and doesn't replace the committed run. A job the slide gave up on may still finish on IBM; the server saves it if it finishes while the server is still running. Ctrl-C stops the server and lists any jobs that hadn't finished.

Plain `npm run preview`, `demo/index.html`, and the phone site never show the live button.

### Offline data

```sh
python -m pipeline.tasks make-sample                                # SYNTHETIC sample in data/sample/synthetic-v1/
python -m pipeline.tasks collect-classical --run <run_id>           # classical stream for an existing run
python -m pipeline.tasks collect-classical --sample <name> --bits N # standalone classical stream
```

## Troubleshooting

**`python3.13: command not found`, or the venv has Python 3.9.** On macOS, bare `python3` is often Apple's Python 3.9, which is too old (`setup-check` says so and fails). Install 3.13 from python.org or Homebrew (`brew install python@3.13`), or use Anaconda's, then recreate the venv: `rm -rf .venv && python3.13 -m venv .venv`, and install again.

**`setup-check` warns that pytest, mypy, or ruff resolve outside `.venv`.** Another environment, usually conda's `base`, is ahead of `.venv` on your PATH, so plain `pytest` runs conda's copy with conda's packages. Run `conda deactivate` and then `source .venv/bin/activate` (and `conda config --set auto_activate_base false` to stop `base` starting in every terminal), or run the tools as `python -m pytest`, `python -m mypy`, `python -m ruff`. A venv *created from* Anaconda's Python is fine; only where the tools resolve matters.

**`ModuleNotFoundError: No module named 'pipeline'` outside the repo root, or `setup-check` reports a HIDDEN `.pth` file.** The editable install works through a `.pth` file in `.venv/lib/python3.13/site-packages/`. If macOS has set the hidden flag on it (sync services and some copy tools do), Python 3.13 skips it. `setup-check` prints the exact fix; it is:

```sh
chflags nohidden .venv/lib/python3.13/site-packages/*.pth
```

**Files changing on their own, or `node_modules` errors after a sync.** The clone is inside iCloud Drive or OneDrive. Move it to a folder that isn't synced (such as `~/code/`), then delete and recreate `.venv` and `ui/node_modules`.

**`npm audit` warnings.** The known warnings are in `vite-plugin-singlefile`'s build-time dependencies (`micromatch`, `braces`). They run only when building `demo/index.html` and are not part of any bundle a browser loads. Don't run `npm audit fix --force`: it downgrades `vite-plugin-singlefile`.

## Working with Claude Code

`CLAUDE.md` has the rules Claude follows here, and `.claude/settings.json` has deny rules that back them up. Claude never runs real collection, `refresh`, or the live server, never reads `~/.qiskit`, never deploys, and never pushes. It commits locally, and you review and push.
