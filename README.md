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

Run the same steps on both Macs. You need Python 3.11+ and Node 20.19+ (or 22.12+).

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
(cd ui && npm run dev)                 # UI dev server
(cd ui && npm run build)               # UI single-file build into ui/dist/
```

More tasks (`analyze`, `build-demo`, `collect-quantum`, ...) are listed in SPEC.md, Section 10, and will be added as they are built.

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
