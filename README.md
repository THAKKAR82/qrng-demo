# qrng-demo

A short live demo showing that quantum computers are usable today, and that quantum random bits are unpredictable in a way Python's default random number generator is not. SPEC.md explains the claim, the metric, and the honesty rules.

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
| `scratch/` | Local only (gitignored) |

## Setup on macOS

Run the same steps on both Macs. You need Python 3.11+ and Node 24+ (both Macs use the version in `.nvmrc`, currently 26.3.0).

```sh
git clone <private-repo-url> qrng-demo
cd qrng-demo

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt

(cd ui && npm ci)

pre-commit install
python -m pipeline.tasks setup-check
```

`setup-check` prints Python, Node, and package versions and flags anything missing or different from the pins. It does not touch IBM credentials. If both Macs report `OK`, they are in sync.

## Everyday commands

```sh
source .venv/bin/activate
python -m pipeline.tasks setup-check   # versions only
pytest                                 # tests (never contact IBM Quantum)
ruff check . && ruff format --check .  # lint
mypy                                   # type check
pre-commit run --all-files             # secret scan, ruff, mypy, hygiene
python -m pipeline.tasks ui-dev        # UI dev server
python -m pipeline.tasks ui-build      # single-file demo/index.html
```

More tasks (`analyze`, `build-demo`, `collect-quantum`, ...) are listed in SPEC.md, Section 10, and will be added as they are built.

## The web app

The app in `ui/` has two parts (SPEC.md, Section 9): the **presenter view**, a slide deck for the projector, and the **phone version**, two short games for the audience. Use the Node version in `.nvmrc` (`nvm use`).

| Command | Use it for |
|---|---|
| `cd ui && npm run dev` | Working on the UI. Same as `python -m pipeline.tasks ui-dev`. |
| `cd ui && npm run preview` | **Presenting.** Builds into `ui/dist/` and serves it at the URL it prints. |
| `cd ui && npm run build:demo` | The fallback: one self-contained `demo/index.html` that opens by double-click, offline. Same as `python -m pipeline.tasks ui-build`. |
| `cd ui && npm run build:web` | **The phone site.** Only the phone version, in `ui/dist-web/`, with `index.html` at the root. Upload that folder to any static host. `npm run preview:web` serves it locally. |

The presenter view opens on slide 1 of the ten-slide talk (SPEC.md, Section 9.4; slide 10 is an appendix for questions). Some slides have steps: "next" first reveals the next part of the slide. Every slide has presenter notes.

Keys in the presenter view: → / ↓ / PageDown / Space next, ← / ↑ / PageUp back, Home and End, N presenter notes, F fullscreen, P the primitives page, Q a large QR code for phones (Q again or Escape closes it). Clickers that send PageUp and PageDown work as-is. On the interactive slides: 0 and 1 enter the room's guess, R reveals the pictures, and M switches between the classical and quantum machines. Add `#primitives` (or `?primitives`) to the URL to open the primitives page directly; it works under `file://` too.

### Phones and the QR code

The phone version has an intro, two games (Spot the quantum machine; Beat the attacker), and a closing screen. It has no slides, notes, or presenter keys, and it is not connected to the presenter's laptop. In the presenter builds the same screens open with `?view=audience`.

The QR code (on slide 1, slide 8, and the Q overlay) shows `VITE_AUDIENCE_URL`, which is read **when you build**. It is drawn in the app; no online service is involved. With no setting, those places show no code.

**For a rehearsal on the local network**, point phones at the laptop. Find the laptop's address (`ipconfig getifaddr en0` on macOS, or the "Network" line that `npm run preview -- --host` prints), then build and serve with it, and connect the phones to the same Wi-Fi:

```sh
cd ui
VITE_AUDIENCE_URL='http://192.168.1.20:4173/?view=audience' npm run preview -- --host
```

**For the real talk**, host the phone site and build the deck with its address:

```sh
cd ui
npm run build:web                                   # upload ui/dist-web/ to your static host
VITE_AUDIENCE_URL='https://example.org/qrng/' npm run preview      # or npm run build:demo
```

Every build uses whatever `ui/src/data/demo.json` holds; `python -m pipeline.tasks export` refreshes it. If the data is synthetic, a label saying so stays on every screen, phone screens included.

To check the UI visually (development only; downloads browsers once with `npx playwright install chromium`):

```sh
cd ui
npm run preview                                    # in one terminal
node scripts/verify.mjs --url http://localhost:4173/ --synthetic no
npm run build:demo && node scripts/verify.mjs --file ../demo/index.html --synthetic no
npm run preview:web -- --port 4174                 # in another terminal
node scripts/verify.mjs --web http://localhost:4174/ --synthetic no
```

The verifier walks every slide and step and every primitive at 1920×1080 and 1280×720, drives each panel, checks slide 8 and the Q overlay, and plays both phone games at 390×844 with touch, including real touch scrolling. With `--web` it checks only the phone site, and also that its bundle holds no presenter content. Add `--qr yes` when the build has a `VITE_AUDIENCE_URL`, or `--qr no` when it doesn't. Screenshots land in `data/scratch/ui-verify/`.

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

Only the human runs real collection. It is interactive by design: it confirms the Open Plan (`plan` must be exactly `open` and `pricing_type` exactly `free`; if the API can't tell, you are asked to type `open plan`), checks the remaining allowance, shows a summary with a rough QPU-time estimate, and asks you to type the backend name before it submits anything. See SPEC.md, Section 6.3.

```sh
source .venv/bin/activate
python -m pipeline.tasks collect-quantum --dry-run   # offline: real Sampler on Aer with a fake backend
python -m pipeline.tasks collect-quantum             # real: 100 lowest-readout-error qubits, 2,000 shots
```

If anything goes wrong after the job is submitted (you press Ctrl-C while it waits, the network drops, or writing fails), the collector prints a recovery command. Run it to write the run folder from the finished job without submitting anything new:

```sh
python -m pipeline.tasks collect-quantum --from-job <job_id>
```

This works best on the Mac that submitted the job, which keeps a submission record in `data/scratch/pending/`. On the other Mac, also pass `--physical-qubits` with the list from the submission summary.

Useful flags: `--shots N`, `--qubits N`, `--backend ibm_fez`, `--no-qubit-selection`, `--physical-qubits 3,7,12`. The run lands in `data/runs/<UTC time>_<backend>/` with `quantum.npz`, `quantum.json`, and the matching `classical.npz` and `classical.json`. Commit that folder.

### Offline data

```sh
python -m pipeline.tasks make-sample                                # SYNTHETIC sample in data/sample/synthetic-v1/
python -m pipeline.tasks collect-classical --run <run_id>           # classical stream for an existing run
python -m pipeline.tasks collect-classical --sample <name> --bits N # standalone classical stream
```

## Working with Claude Code

`CLAUDE.md` has the rules Claude follows here, and `.claude/settings.json` has deny rules that back them up. Claude never runs real collection, never reads `~/.qiskit`, and never pushes. It commits locally, and you review and push.
