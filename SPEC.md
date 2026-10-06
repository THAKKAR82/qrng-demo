# QRNG Demo: Specification

This document is the source of truth for the project. If code, copy, or charts disagree with it, the code, copy, or charts are wrong. Change this document first, then the code.

## 1. Purpose and audience

This is a short live demo for a mixed audience of technical and non-technical people. It has to land two points:

1. **Quantum computers are real and usable today.** We run a small job on a real IBM Quantum processor and show the real job: backend name, job ID, timestamp, and the physical qubits used.
2. **Quantum random bits are unpredictable in a way that an ordinary classical random number generator is not.** We prove this by attacking both and measuring how well the attacker does.

The demo has three parts: a Python pipeline that collects and analyses data, a Jupyter notebook that walks through the analysis end to end, and a presentation web app that shows the results. The web app is built into a single HTML file that runs offline on stage.

## 2. The core claim

By ordinary statistics, both sources look random. In both streams roughly half the bits are 1, and the Shannon entropy is close to 1 bit per bit. Ordinary statistics cannot tell them apart, and the demo should say so plainly.

The difference is **predictability**.

- **Classical stream.** Python's `random` module uses the Mersenne Twister (MT19937). Its whole internal state is 624 32-bit words, and every output is a fixed, invertible function ("tempering") of one state word. An attacker who sees 624 consecutive 32-bit outputs can undo the tempering, rebuild the full state, and then predict every later output exactly. Their accuracy on future bits is 100%.
- **Quantum stream.** Each bit comes from measuring a qubit put into an equal superposition. No hidden state determines the outcome, so the attacker can do no better than learn each qubit's bias and always guess that qubit's more common value. Real hardware has readout bias (for example, a qubit that reads 1 about 40% of the time), so this attacker does somewhat better than 50%, but nowhere near 100%.

## 3. Key metric: min-entropy from the attacker's point of view

The headline number is **min-entropy**, measured against a concrete attacker:

```
H∞ = −log2(max(P_guess, 1 − P_guess))
```

`P_guess` is the attacker's measured accuracy on bits they did not see: the fraction of held-out bits they predicted correctly. H∞ is in bits of unpredictability per bit of output. An attacker who is reliably wrong is as good as one who is reliably right, because flipping every guess turns accuracy P_guess into 1 − P_guess; so the effective guessing probability is max(P_guess, 1 − P_guess). H∞ = 0 means fully predictable (P_guess = 1 or 0); H∞ = 1 means a coin flip (P_guess = 0.5). H∞ never exceeds 1 bit.

**Shannon entropy** is reported as well, so the audience can see that ordinary statistics don't separate the two sources. For a stream whose fraction of ones is p̂, the per-bit Shannon entropy is `h(p̂) = −p̂·log2(p̂) − (1−p̂)·log2(1−p̂)`. For the quantum stream, report it per physical qubit and also as the mean across qubits. The per-qubit figure is the honest one, because pooling qubits with opposite biases hides those biases.

### 3.1 Attackers

Each attacker sees a training portion of a stream and predicts the held-out portion. The attacker never sees the classical seed, only the outputs.

- **State-recovery attacker (classical).** It observes the first 624 consecutive 32-bit words. It untempers each word to recover the MT19937 state (624 words), then runs the generator forward to predict every later word. P_guess is the fraction of held-out *bits* predicted correctly, so the unit matches the quantum stream.
- **Bias attacker (quantum).** It observes the first half of the shots. For each physical qubit it estimates P(1) and then predicts that qubit's more common value on every held-out shot. P_guess is the fraction of held-out bits predicted correctly, pooled over all qubits. Per-qubit accuracies are reported too.
- **Cross-checks (fairness).** Run each attacker against the other stream as well. The state-recovery attacker run on quantum bits (packed into 32-bit words the same way) should score about 50%, and the bias attacker run on classical bits should score about 50%. These cross-checks show that neither attacker was tuned to make one source look bad. They appear in the notebook and in the presenter notes.

### 3.2 Uncertainty and limits

- Report a 95% Wilson confidence interval for every P_guess. Report H∞ at the point estimate and, conservatively, at whichever interval bound gives the larger max(P_guess, 1 − P_guess), which is the lower H∞. A P_guess slightly below 0.5 is sampling noise and should be described that way.
- H∞ measured this way is min-entropy *against these attackers*. It is not a certified, device-independent bound. A cleverer attacker might exploit drift over time or correlations between qubits. The notebook must include at least one simple extra attacker (predict each qubit's bit from its previous shot) to show such effects are small in our data, or to report them if they aren't.

### 3.3 What to expect

The classical stream should come out at H∞ ≈ 0 bits, because the state-recovery attacker should reach 100% accuracy. The quantum stream should come out well above 0 bits.

All values come from data. None may be hard-coded, used as a test expectation, or written into copy (see Section 4).

*Context only, not an expectation:* the first real run, `2026-10-06T013454Z_ibm_fez` (100 qubits selected by lowest readout error from 156, 2,000 shots), measured a bias-attacker P_guess of 0.50396 (95% CI 0.50086–0.50706), so H∞ = 0.989 bits (0.980 at the conservative bound). Per-qubit Shannon entropy averaged 0.99937 bits; per-qubit P(1) ranged from 0.4605 to 0.5385. The classical stream's attacker scored 1.0, so H∞ = 0. Other runs, days, backends and qubit choices will differ.

## 4. Honesty rules

These rules apply to all code, copy, charts, notebook text, and presenter notes.

1. **Never present simulator or synthetic output as quantum hardware output.** Synthetic data must be labelled synthetic everywhere it appears: file metadata, notebook output, every chart title, and a persistent on-screen banner in the UI.
2. **Never claim quantum bits have higher Shannon entropy.** They don't; with readout bias, their Shannon entropy is usually slightly *lower*. The claim is about predictability only.
3. **Every on-screen number and every comparative phrase comes from the data**, never from assumptions. Copy is written as templates filled from `results.json` (or `demo.json`, which the same analysis code produces). Words such as "much more" or "slightly" are chosen by rules in the analysis code, applied to measured values.
4. **The attacker never sees the classical seed**, only the outputs. The seed is never stored, logged, or returned.
5. **If qubits are selected by readout error, say so on screen**, along with how many candidates they were picked from.
6. **Hardware bias, if visible, is explained, never hidden or post-processed away.** No readout-error mitigation, no measurement twirling, no randomness extraction, and no debiasing is applied to the bits we report. The UI explains bias in plain language (the detector reads 0 slightly more easily than 1).
7. **Secure classical generators are also unpredictable in practice.** `os.urandom` and other cryptographically secure generators cannot be predicted by any known practical attack. Their guarantee rests on computational hardness, while the quantum guarantee rests on physics. Mersenne Twister is used because it is the default `random` module that many programs reach for, not because it represents the best classical option. This goes in the notebook appendix and the presenter notes, and the UI must not imply that all classical randomness is predictable.

## 5. Data definitions

### 5.1 Classical stream

- The generator is `random.Random`, seeded with 32 bytes from `os.urandom` (converted with `int.from_bytes(..., "big")`).
- The seed is discarded immediately after constructing the generator. It is never written to disk, logged, returned, or stored in metadata.
- Each output word comes from `getrandbits(32)`, which consumes exactly one MT19937 output. Store the words as `uint32`.
- Each word is unpacked to bits **most significant bit first**. Word `w` gives bits `(w >> 31) & 1, (w >> 30) & 1, …, w & 1`.
- The stream has the same number of bits as the quantum stream it is compared with, rounded up to a whole number of words.

### 5.2 Quantum stream

- **Circuit:** a Hadamard gate then a measurement on each of N selected physical qubits. Qubit i in the logical circuit is measured into classical bit i.
- **Backend:** a real IBM Quantum backend (`simulator=False`, operational). Never a simulator or a fake backend for anything written to `data/runs/`.
- **Execution:** the client-side `Sampler` from `qiskit_ibm_runtime.executor_sampler` in job mode (a single job, not a session). In qiskit-ibm-runtime 0.50 the old `SamplerV2` is deprecated and this is its named replacement. No error mitigation, no gate or measurement twirling, no dynamical decoupling. Every Sampler option is set explicitly rather than left to defaults, and the full option set is recorded in `quantum.json`.
- **Bit order:** Qiskit bitstrings are little-endian. In the string `"001"`, the rightmost character is classical bit 0, so classical bit 0 = 1. Do not index bitstrings directly. Convert with `BitArray.to_bool_array(order="little")`, which gives an array of shape `(shots, N)` whose column `j` is classical bit `j`, and therefore logical qubit `j`, and therefore physical qubit `physical_qubits[j]`. Unit tests must pin this with a hand-written example.
- **Flattening:** shot-major order, meaning all N qubits of shot 1, then all N qubits of shot 2, and so on. With the `(shots, N)` array, this is `bits.reshape(-1)` in NumPy's default C order.
- **Metadata** keeps the physical qubit for every column, so per-qubit analysis is always possible.

### 5.3 Run folders

Each real collection run is a committed folder `data/runs/<run_id>/`, where `run_id` is `YYYY-MM-DDTHHMMSSZ_<backend>` (UTC), for example `2026-10-06T141500Z_ibm_fez`. Run folders are never overwritten or edited after the run; reanalysis only adds or replaces `results.json`.

| File | Contents |
|---|---|
| `quantum.npz` | `bits`: `uint8`, shape `(shots, N)`, values 0/1, columns in logical-qubit order. |
| `quantum.json` | Everything needed to interpret the quantum bits (below). |
| `classical.npz` | `words`: `uint32`, shape `(n_words,)`, in generation order. |
| `classical.json` | Everything needed to interpret the classical words (below). |
| `results.json` | Output of `analyze` (Section 7). |

Neither JSON file ever contains any key, token, CRN, or instance name. Run folders are committed, so the collector warns if a folder exceeds 10 MB.

`quantum.json` contains:

- `schema_version`, `run_id`, `created_utc`
- `source`: `"ibm_quantum_hardware"` or `"synthetic"`, and a boolean `synthetic`
- `recovered`: `true` if the folder was written by `collect-quantum --from-job` (Section 6.3), with a `recovery` block saying when and from which record; otherwise `false` and `null`
- `backend`: name and qubit count; `plan`: the `plan` and `pricing_type` values checked, and how they were verified (`"api"` or `"human_typed_open_plan"`)
- `job`: job ID, shots, submit and completion times, and QPU seconds used (if the job reports them)
- `qubits`: a list with one entry per column: `column`, `physical_qubit`, and `readout_error` at selection time
- `qubit_selection`: whether selection by readout error was used, `method` (`"lowest_readout_error"`, `"first_n"`, or `"explicit"`), number of candidates considered, and the calibration timestamp used
- `circuit`: plain description, optimization level, and gate counts after transpilation
- `sampler`: the Sampler class and its full, finalized option set, plus explicit flags for readout-error mitigation, gate twirling, measurement twirling, and dynamical decoupling (all `false`)
- `software`: Python, numpy, qiskit, and qiskit-ibm-runtime versions

`classical.json` contains `schema_version`, `run_id`, `created_utc`, `synthetic`, generator `"random.Random (MT19937)"`, seed source `"os.urandom"`, `seed_stored: false`, `seed_discarded: true`, word count, word size 32, bit order `"msb_first"`, the number of bits it was matched to, and the number of bits generated.

### 5.4 Synthetic sample data

`data/sample/<name>/` (starting with `data/sample/synthetic-v1/`) uses exactly the same file layout so the notebook, tests, and UI can run without hardware. Its quantum-like bits are independent Bernoulli draws from NumPy with a fixed per-column P(1) around 0.45 and a fixed seed, and both `quantum.json` and `classical.json` say `synthetic: true` (and `quantum.json` says `source: "synthetic"`). Fake physical-qubit numbers are not used; the qubit list says `"synthetic"` instead. Its classical stream is produced exactly as in Section 5.1. Sample data is regenerated only by `make-sample`.

`data/scratch/` is gitignored and holds temporary outputs (executed notebooks, experiments).

## 6. IBM Quantum access and cost safety

### 6.1 Credentials

- Credentials are a Qiskit saved account named `qrng-open` in `~/.qiskit`, pinned to a free Open Plan instance. The name can be overridden with the environment variable `QRNG_IBM_ACCOUNT`.
- Code loads the account only with `QiskitRuntimeService(name=<account name>)`. The repository never contains, reads, prints, or logs API keys or instance CRNs. Code never calls `save_account`, never prints `active_account()`, `saved_accounts()`, `instances()`, or `active_instance()`, and never opens files in `~/.qiskit` directly.
- Exceptions from qiskit-ibm-runtime can contain URLs that include the CRN. The collector catches them and prints the exception type plus a message in which anything matching `crn:` or a long token-like string is redacted.

### 6.2 Shared free allowance

Both machines use the same account and share one free Open Plan allowance of 10 minutes of QPU time per 28 days. One run with the default settings should use a few seconds. Real collection is run by the human only, deliberately.

### 6.3 The collection task (`collect-quantum`)

This task runs on the human's machine only. It is never run by Claude, CI, or tests. In order, it:

1. **Refuses to run non-interactively.** It requires stdin to be a TTY, so tool-driven shells cannot run it.
2. Loads the account by name (Section 6.1).
3. **Confirms the Open Plan.** It finds the entry in `service.instances()` whose `crn` equals `service.active_instance()`. (In qiskit-ibm-runtime 0.50, each entry carries `plan`, the lowercased catalog display name, and `pricing_type`.) The human's manual check (README) on the `qrng-open` account returned exactly `plan == "open"` and `pricing_type == "free"`, so:
   - If both values are reported and are exactly `"open"` and `"free"`, it prints "Open Plan: confirmed" and continues.
   - If either value is reported and is anything else (a different string, different case, or a non-string), it refuses and aborts.
   - If the plan **cannot be determined** (the API call fails, no single entry matches the active instance, or either value is missing), it says so and asks the human to type `open plan` to confirm. Anything else aborts. The run's `quantum.json` records that the plan was confirmed by the human rather than by the API.

   It never prints the CRN or instance name. If the account starts returning different strings, update this section first.
4. **Checks the remaining allowance.** It calls `service.usage()` and aborts if `usage_remaining_seconds` is missing or below 60 seconds.
5. Picks the backend: `--backend <name>` if given, otherwise `service.least_busy(operational=True, simulator=False)`. It refuses a simulator.
6. Picks qubits. N is `--qubits N` (capped at the backend's size). By default it takes the N qubits with the lowest measurement error in `backend.target["measure"]` at submission time, skipping qubits with no reported error. `--no-qubit-selection` disables this and uses physical qubits `0 … N−1`; `--physical-qubits 3,7,12` selects explicitly. Either way it records each chosen qubit's readout error and the calibration time.
7. Builds and transpiles the circuit with `generate_preset_pass_manager(optimization_level=1, backend=backend, initial_layout=<qubits>)`, then checks the layout of the transpiled circuit matches the requested physical qubits.
8. **Shows a summary and asks for confirmation:** backend, qubits, shots, a rough QPU-time estimate, and remaining allowance. The human must type the backend name to proceed.
9. Submits one Sampler job (Section 5.2) and prints the job ID immediately. It saves the submission record (everything `quantum.json` will hold that is known at submission) to `data/scratch/pending/<job_id>.json`, which is gitignored and local to that Mac. It polls with a one-line status display until the job finishes, converts the result as described in Section 5.2, and writes `quantum.npz` and `quantum.json` (including the QPU usage the job reports) to a new run folder. It then generates the matching classical stream into the same folder (`classical.npz`, `classical.json`) and deletes the pending record.

If anything fails after submission (the human interrupts the wait, the network drops, or writing fails), the collector removes any partly written run folder, keeps the pending record, and prints the exact recovery command: `python -m pipeline.tasks collect-quantum --from-job <job_id>`. A job that itself ends in `ERROR` or `CANCELLED` is reported as such, with no recovery command, because there is nothing to recover.

Network and authentication failures end with a short, redacted message (Section 6.1), not a traceback.

Defaults: N = 100 qubits (fewer if the backend is smaller), 2,000 shots (200,000 quantum bits).

#### Recovery (`--from-job <job_id>`)

Recovery writes the run folder for a job that was already submitted. It never submits anything, but it loads the saved account, so it is **human only**, just like a real collection, and it also refuses to run without a TTY. It retrieves the job with `service.job(<job_id>)`, waits if the job is still running, and then uses the same result-parsing and writing code as step 9.

- If the pending record exists (the normal case, on the Mac that submitted), it becomes the metadata, so `quantum.json` is identical to a normal run's apart from `recovered: true` and a `recovery` block (`recovered_utc`, and `submission_record: "local pending record"`).
- Without a pending record (for example, on the other Mac), recovery requires `--physical-qubits` in column order, as printed in the submission summary. It runs the Open Plan check (step 3) for the `plan` field, takes readout errors from the backend's calibration at recovery time, and marks anything unknown: `qubit_selection.method: "unknown_recovered"`, Sampler options `null`, and mitigation flags `null`. It sets `submission_record: "reconstructed"`.
- An existing run folder is never overwritten.

Normal runs record `recovered: false` and `recovery: null`.

#### Dry run (`--dry-run`)

The dry run uses no account and no network access, and Claude may run it. It runs steps 5 to 8 against the local fake backend `FakeFez` from `qiskit_ibm_runtime.fake_provider`. It then exercises the real pipeline end to end: it submits the circuit through the **same client-side Sampler** with the same options, polls it, parses the result with the same code as a real run, and writes the complete run folder (quantum and classical files) into a temporary directory that is deleted afterwards. Nothing is written to `data/runs/`.

The Sampler runs locally on Qiskit Aer (a dev dependency). With a fake backend as its mode, the Sampler builds an Aer simulator with the device's full noise model, including thermal relaxation, and that cannot simulate 100 qubits in memory. The dry run therefore gives the Sampler an `AerSimulator` built from `FakeFez` with the same target and that backend's readout and gate errors, but no thermal relaxation, using the stabilizer method. The default 100 × 2,000 run then takes about a second. Its output is simulated and is never kept; the dry-run record is labelled `source: "local_simulator_dry_run"` and `synthetic: true`.

## 7. Analysis

`analyze --run <run_id>` (or `--sample <name>`) reads a run folder and writes `results.json`. The notebook and the UI both use the functions in `pipeline/` for this; no analysis logic is duplicated in the notebook or in TypeScript.

`results.json` contains:

- `source`, `synthetic`, `run_id`, backend, job ID, timestamp, physical qubits, qubit selection method, and candidate count
- For each stream: bit count, fraction of ones, Shannon entropy (pooled, plus per qubit and mean for quantum), attacker name, training and held-out counts, P_guess with its 95% interval, and H∞ at the point estimate and at the conservative bound
- Per-qubit P(1) and per-qubit attacker accuracy for the quantum stream
- Cross-check results (Section 3.1)
- `copy`: comparative phrases chosen by documented rules from the measured values, used verbatim by the UI

### 7.1 Export for the UI (`export`)

`export [--run <run_id> | --sample <name>]` writes `ui/src/data/demo.json`, the only data file the UI imports. By default it uses the latest complete folder in `data/runs/` (run ids start with a UTC timestamp, so the greatest name is the newest); if there is none, it uses `data/sample/synthetic-v1/`. It computes everything with the same `pipeline.analysis` and `pipeline.attacker` functions as `analyze`.

`demo.json` holds: metadata for both sources (backend, job ID, date, qubit count, whether qubits were selected by readout error and from how many candidates, the run folder name, and `synthetic` and `sample` flags); Shannon entropy for each stream (per qubit, mean, and pooled for quantum); per-qubit P(1), readout error, z-score against 0.5, and bias-attacker accuracy; bias summary statistics (mean P(1), mean and worst-case |P(1) − 0.5|); the bias tests below; a 128×128 bitmap of the first 16,384 bits of each stream; the first 200 held-out bits of each stream with the attacker's prediction for each (for an audience guessing game); and both attackers' accuracy, 95% Wilson interval, H∞ at the point estimate and at the conservative bound, and running accuracy downsampled to at most 500 points; and the cross-checks from Section 3.1, each with its accuracy, 95% interval, and whether the interval contains 0.5.

**Bias tests.** For each qubit, z = (P(1) − 0.5) / √(0.25 / shots); qubits with |z| > 3 are listed. A chi-square test (shots·Σ(p̂ⱼ − p̄)² / (p̄(1 − p̄)), N − 1 degrees of freedom) asks whether per-qubit P(1) values spread more than shot noise predicts. The overall mean P(1) is tested against 0.5 both as a pooled binomial z (which assumes all qubits share one P(1)) and as a one-sample t-test across the per-qubit values (which does not). **Flagged qubits are reported, never dropped or filtered.**

The schema is `ui/src/data/demo.schema.json`, documented in `ui/src/data/SCHEMA.md`. Every object in it is closed. Fields are copied from run metadata by an explicit allow-list. Before writing, `export` validates against the schema, refuses output that contains anything secret-like (`crn:`, the account name, `.qiskit`, long token-like strings, or local file paths), and refuses output of 1 MB or more.

## 8. Notebook

There is one notebook, `notebooks/qrng_analysis.ipynb`. It runs the analysis end to end by calling `pipeline` functions:

1. Load a run (the latest committed real run by default; otherwise the synthetic sample, with a visible "SYNTHETIC DATA" banner in its output).
2. Show bit ordering and flattening on a small example.
3. Show that both streams look random by ordinary statistics: fraction of ones and Shannon entropy.
4. Run both attackers and the cross-checks, and report P_guess, its confidence interval, and H∞.
5. Plot per-qubit bias, with an explanation of readout bias.
6. **Appendix:** secure classical generators (`os.urandom`), the computational-hardness vs. physics distinction, and the limits from Section 3.2.

The notebook is committed with outputs cleared. Tests execute it against the synthetic sample (with `nbmake`) so it can't silently break.

## 9. Presentation UI

`ui/` is a Vite + React + TypeScript app. At build time it imports `ui/src/data/demo.json` (Section 7.1), exported from one run, so the built page needs no network and no server. `vite-plugin-singlefile` inlines everything into one HTML file, which the `build-demo` task copies to `demo/index.html` (committed).

The screens, in order:

1. **This ran on a real quantum computer:** backend, job ID, date, and the physical qubits used, with a note that they were selected by lowest readout error.
2. **Both look random:** fraction of ones and Shannon entropy side by side, nearly identical.
3. **The attack:** the attacker sees 624 words of classical output and then predicts the rest; for quantum, it learns each qubit's bias and guesses. Show both accuracies.
4. **The result:** H∞ for both streams, with confidence intervals.
5. **Why quantum isn't 50/50:** readout bias, explained plainly, with the per-qubit chart.

Presenter notes, including the `os.urandom` point and the cross-checks, are in a panel toggled with the N key and hidden by default. If `demo.json` says `synthetic: true`, a banner reading "SYNTHETIC DATA: not from quantum hardware" stays on every screen and can't be dismissed.

## 10. Tasks

Everything runs through `python -m pipeline.tasks <task>`.

| Task | What it does | Who runs it |
|---|---|---|
| `setup-check` | Reports Python, Node, and package versions against the pins. Touches no credentials. | Anyone |
| `make-sample` | Regenerates `data/sample/synthetic-v1/`. | Anyone |
| `collect-classical --run <id>` / `--sample <name> [--bits N]` | Adds `classical.npz` and `classical.json` to a run (matching its quantum bit count), or generates them standalone into `data/sample/<name>/`. | Anyone |
| `collect-quantum` | Real hardware collection (Section 6.3). | **Human only** |
| `collect-quantum --from-job <id>` | Writes the run folder for an already-submitted job; submits nothing (Section 6.3). | **Human only** |
| `collect-quantum --dry-run` | Runs the real Sampler locally on Aer with a fake backend; writes nothing to `data/runs/`. | Anyone |
| `analyze --run <id>` / `--sample <name>` | Writes `results.json`. | Anyone |
| `export [--run <id> \| --sample <name>]` | Writes `ui/src/data/demo.json` (Section 7.1). | Anyone |
| `notebook` | Executes the notebook into `data/scratch/`. | Anyone |
| `ui-dev` | Starts the Vite dev server. | Anyone |
| `build-demo --run <id>` | Builds the UI from one run and copies it to `demo/index.html`. | Anyone |
| `check` | Runs ruff, mypy, pytest, and the UI lint and type check. | Anyone |
| `refresh` | Runs `collect-quantum`, `analyze`, and `build-demo` in one go. | **Human only** |

`setup-check`, `make-sample`, `collect-classical`, `collect-quantum`, and `export` exist so far. The others are added in later tasks.

## 11. Engineering conventions

- **Platforms:** both machines are macOS, and the workflow must behave identically on both. Use `pathlib` for all paths and resolve them from the repo root (`pipeline/paths.py`), never from the current directory.
- **Python:** 3.11 or newer. Use a plain `python -m venv .venv` and `pip`. Exact pins are in `requirements.txt` (runtime) and `requirements-dev.txt` (tools, plus the package in editable mode); `pyproject.toml` holds compatible ranges and tool configuration.
- **Node:** version 20.19 or newer (or 22.12 or newer). UI dependencies are pinned exactly in `ui/package.json`, with `ui/package-lock.json` committed. Install with `npm ci`.
- **Quality checks:** ruff for linting and formatting, mypy in strict mode, and pytest. Pre-commit runs detect-secrets, ruff, mypy, and basic hygiene hooks.
- **Tests never touch IBM Quantum.** Collector tests use a mocked `QiskitRuntimeService`; the Sampler is either mocked or the real client-side Sampler running locally on Aer (`qiskit-aer`, a dev dependency). They must cover refusal on a non-Open-Plan instance, refusal on low remaining allowance, the bit-order conversion, and that no CRN or token appears in output.
- **Version control:** run folders, sample data, the notebook (outputs cleared), and `demo/index.html` are committed. `data/scratch/`, `scratch/`, `.env*`, and virtualenvs are not.
