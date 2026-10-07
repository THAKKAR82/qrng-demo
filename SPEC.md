# QRNG Demo: Specification

This document is the source of truth for the project. If code, copy, or charts disagree with it, the code, copy, or charts are wrong. Change this document first, then the code.

## 1. Purpose and audience

This is a short live demo for a mixed audience of technical and non-technical people. It has to land two points:

1. **Quantum computers are real and usable today.** We run a small job on a real IBM Quantum processor and show the real job: backend name, job ID, timestamp, and the physical qubits used.
2. **Quantum random bits are unpredictable in a way that an ordinary classical random number generator is not.** We prove this by attacking both and measuring how well the attacker does.

The demo has three parts: a Python pipeline that collects and analyses data, a Jupyter notebook that walks through the analysis end to end, and a web app that shows the results. The web app is a hybrid of a presentation and an app: the presenter drives a slide deck on a projector, some slides contain interactive panels, and audience members can optionally play two short games on their phones (Section 9).

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
3. **Every on-screen number and every comparative phrase comes from the data**, never from assumptions. Copy is written as templates filled from `results.json` (or `demo.json`, which the same analysis code produces). Words such as "much more" or "slightly" are chosen by rules in the analysis code, applied to measured values. The one other source is an optional live run (Section 6.4). Its numbers come from the live server's response, computed in Python by `pipeline.analysis`, and are always labelled as a live run. No comparative phrase is ever chosen for a live run.
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

`data/live/` is gitignored and holds live runs from the presenter's laptop (Section 6.4). It is never read by `export` or the notebook, and nothing in it replaces the main dataset.

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

### 6.4 Live mode (`live-server`)

An optional live run on slide 3 (Section 9.5, Machines), with the recorded run as fallback. It runs only on the presenter's laptop, through `python -m pipeline.tasks live-server`, which is **human only**, like `collect-quantum`. The live control never appears in the phone site (`build:web`), the single-file build (`build:demo`, opened under `file://`), or plain `npm run preview`.

**Serving.** `live-server` serves the existing presenter build in `ui/dist/` and a small JSON API from the same origin. It never builds the app itself (`npm run build` does), and refuses to start if `ui/dist/index.html` is missing. It binds to `127.0.0.1` only. There is no option to bind to another interface, and it refuses to start if asked to (`--host`, `--bind`). The default port is 8765 (`--port N`). Because the QR codes come from the last build, it prints at startup whether the served build has `VITE_AUDIENCE_URL` set, and to what, or that it is unset. The build records the setting in a `<meta name="qrng-audience-url">` tag for this purpose.

**Arming** at startup reuses the collector's code and safeguards from Section 6.3:

1. It refuses to start without an interactive terminal (stdin a TTY).
2. It loads the account by name, runs the Open Plan check (step 3), and runs the allowance check (step 4). The allowance must also cover every live run at its maximum execution time (3 × 30 s).
3. It picks the backend (`--backend <name>`, otherwise the least busy; never a simulator) and the 10 qubits with the lowest readout error, then builds and transpiles the circuit once (steps 5 to 7).
4. It shows the live configuration: backend, the 10 qubits and their readout errors, 200 shots per run (2,000 bits), at most 3 live runs in this server session, a `max_execution_time` of 30 s per run, and the remaining allowance. The human must type the backend name to arm.

If a check fails, the account can't be loaded, or the human types anything else, the server still starts, **unarmed**. It serves the presenter app, and the health endpoint reports live mode unavailable. The terminal gets a short, redacted reason; the API never does.

Each live run is one Sampler job (not a session) with the circuit, Sampler class, and explicit options of Section 5.2, except `default_shots` 200, `max_execution_time` 30, and the job tags `qrng-demo` and `live`. No mitigation, twirling, or debiasing, as always.

**API.** All JSON, under `/api/live/`:

| Request | What it does |
|---|---|
| `GET /api/live/health` | `armed`, `backend` (or `null`), `runs_remaining`, `max_runs`, `shots`, `n_qubits`. |
| `POST /api/live/runs` | Starts a live run and returns its id at once; submission happens in the background. Refused when unarmed, when the cap is reached, or while another live run is still in progress. The request body is ignored: the client chooses nothing. |
| `GET /api/live/runs/<id>` | The run's stage: `submitting`, `submitted` (with the job ID), `queued` (with seconds elapsed), `running`, `done`, or `failed` (with a short redacted reason). The job ID is included as soon as it exists. On `done` it also returns the bits (shot-major, packed like a pool in Section 7.1), shots, qubit count, physical qubits, the qubit selection method and candidate count (shown on screen, Section 4.5), per-qubit P(1), fraction of ones, Shannon entropy (pooled and per-qubit mean), the job ID, submit and completion times, and the QPU seconds the job reports. |

The run cap counts every accepted start, whatever happens to that run. The server keeps watching a job after the app has given up on it, and saves it if it finishes. It never cancels a job. On shutdown it prints the job IDs of any live runs still in progress.

**Saving.** Each finished live run is written to `data/live/<run_id>/` (with `run_id` as in Section 5.3): `quantum.npz` and `quantum.json` in the format of Section 5.3, with `"live": true` and no classical files. `data/live/` is gitignored and never read by `export` or the notebook, and `export` refuses any folder whose `quantum.json` says `live: true`.

**Local server security.** Other websites open in the same browser must not be able to start IBM jobs.

- At startup the server generates a random per-session token and embeds it in the presenter page it serves (`<meta name="qrng-live-token">`). Every API request must carry it in the `X-QRNG-Live-Token` header, compared in constant time. Requests without it, or with a wrong one, are rejected.
- Every request, the page included, is rejected unless its `Host` header is exactly `127.0.0.1:<port>` or `localhost:<port>` (against DNS rebinding). A request whose `Origin` header is present but isn't the server's own origin (`http://` plus that `Host`) is rejected too.
- No CORS headers at all. Each path answers only the methods it needs (GET and HEAD for the app's files, GET for health and run status, POST to start a run). Everything else, `OPTIONS` included, gets 405.
- Pages are sent with `Cache-Control: no-store`, `X-Frame-Options: DENY`, a `frame-ancestors 'none'` content security policy, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: no-referrer`, so no other site can embed the page and trick a click.
- Responses and errors never include credentials, CRNs, account names, or local file paths. Messages pass through the collector's redaction (Section 6.1), and every JSON response is checked with the export's secret scan (Section 7.1) before it is sent. A response that fails is replaced by a generic error.
- The arming requirement and the run cap are enforced by the server, whatever the client sends.

**In the app.** The presenter app looks for the token meta tag. With none (plain preview, `file://`), it makes no request and shows no live control. The single-file build doesn't contain the live code at all, and the phone site never imports slide code. With a token, the app asks the health endpoint once when it loads, and shows the control only if the server is armed with runs remaining. What the control does is in Section 9.5.

## 7. Analysis

`analyze --run <run_id>` (or `--sample <name>`) reads a run folder and writes `results.json`. The notebook and the UI both use the functions in `pipeline/` for this; no analysis logic is duplicated in the notebook or in TypeScript.

**One exception: display-only counting in the UI.** When the UI streams bits live from a pool (Section 7.1), it may compute, over the bits shown so far, only: the fraction of ones, the Shannon entropy h(p̂) of that fraction, and counts of matches (the score of a guessing round). The same applies to the bits of a live run (Section 6.4) as the Machines panel streams them. These live in one file, `ui/src/lib/stats.ts`, are for display only, and are never written back or used to choose wording. A test (`tests/test_ui_stats.py`) runs that file under Node on the exported pool bits and checks its values against `pipeline.analysis` on the same bits. Everything else, including every interval, H∞, running curve, and comparative phrase, is precomputed in Python.

`results.json` contains:

- `source`, `synthetic`, `run_id`, backend, job ID, timestamp, physical qubits, qubit selection method, and candidate count
- For each stream: bit count, fraction of ones, Shannon entropy (pooled, plus per qubit and mean for quantum), attacker name, training and held-out counts, P_guess with its 95% interval, and H∞ at the point estimate and at the conservative bound
- Per-qubit P(1) and per-qubit attacker accuracy for the quantum stream
- Cross-check results (Section 3.1)
- `copy`: comparative phrases chosen by documented rules from the measured values, used verbatim by the UI

### 7.1 Export for the UI (`export`)

`export [--run <run_id> | --sample <name>]` writes `ui/src/data/demo.json`, the only data file the UI imports. By default it uses the latest complete folder in `data/runs/` (run ids start with a UTC timestamp, so the greatest name is the newest); if there is none, it uses `data/sample/synthetic-v1/`. It computes everything with the same `pipeline.analysis` and `pipeline.attacker` functions as `analyze`.

`demo.json` (schema version 2) holds:

- metadata for both sources (backend, job ID, date, qubit count, whether qubits were selected by readout error and from how many candidates, the run folder name, and `synthetic` and `sample` flags);
- Shannon entropy for each stream (per qubit, mean, and pooled for quantum); per-qubit P(1), readout error, z-score against 0.5, and bias-attacker accuracy; bias summary statistics (mean P(1), mean and worst-case |P(1) − 0.5|); the bias tests below;
- a 128×128 bitmap of the first 16,384 bits of each stream (these lie inside each attacker's training data for the default run sizes; export records whether they do);
- **spot images** per stream, for the phone game "Spot the quantum machine": up to ten 64×64 images (4,096 consecutive bits each), from non-overlapping segments spread evenly through the stream outside the pool, each with its starting bit and its bits packed like the pool;
- a **pool** per stream: 20,000 consecutive **held-out** bits starting right after the attacker's training data, with the attacker's prediction for every pool bit, both packed compactly (base64 of the bits packed 8 per byte, most significant bit first). The UI streams and games use only these bits, never repeating or wrapping them. The pool comes only from held-out data: export refuses to write it otherwise;
- both attackers' accuracy, 95% Wilson interval, H∞ at the point estimate and at the conservative bound, and running accuracy downsampled to at most 500 points, with the 95% Wilson interval at every running point;
- the cross-checks from Section 3.1, each with its accuracy, 95% interval, whether the interval contains 0.5, and its running accuracy and interval in the same form;
- the **device layout** when Qiskit ships an offline description of the run's backend (for `ibm_fez`, `FakeFez` from `qiskit_ibm_runtime.fake_provider`, read from files bundled with the package, with no account or network): qubit count, the undirected coupling edges, and drawing coordinates derived offline from the coupling graph. It is labelled on screen as Qiskit's bundled device description, not as live calibration. It is `null` when no such description exists (for example for synthetic data);
- `copy`: comparative phrases chosen by documented rules (`pipeline/wording.py`, described in SCHEMA.md) from the measured values. The UI uses them verbatim and never chooses comparative words itself.

**Bias tests.** For each qubit, z = (P(1) − 0.5) / √(0.25 / shots); qubits with |z| > 3 are listed. A chi-square test (shots·Σ(p̂ⱼ − p̄)² / (p̄(1 − p̄)), N − 1 degrees of freedom) asks whether per-qubit P(1) values spread more than shot noise predicts. The overall mean P(1) is tested against 0.5 both as a pooled binomial z (which assumes all qubits share one P(1)) and as a one-sample t-test across the per-qubit values (which does not). **Flagged qubits are reported, never dropped or filtered.**

The schema is `ui/src/data/demo.schema.json`, documented in `ui/src/data/SCHEMA.md`. Every object in it is closed. Fields are copied from run metadata by an explicit allow-list. Before writing, `export` validates against the schema, refuses output that contains anything secret-like (`crn:`, the account name, `.qiskit`, long token-like strings, or local file paths), and refuses output of 1 MB or more, so the page loads quickly on a phone.

## 8. Notebook

There is one notebook, `notebooks/qrng_demo.ipynb`. It runs the analysis end to end by calling `pipeline` functions, and contains no analysis logic of its own:

1. Load a run, choosing the folder exactly as `export` does (the latest committed real run by default; otherwise the synthetic sample, with a prominent "SYNTHETIC DATA" banner in its output). The environment variables `QRNG_NOTEBOOK_RUN` and `QRNG_NOTEBOOK_SAMPLE` override the choice, like `export --run` and `--sample`.
2. **Proof of hardware:** backend, job ID, timestamps, qubit selection method and candidate count, a small bit-ordering and flattening example, per-qubit P(1) alongside readout error, and the bias tests from Section 7.1 (flagged qubits are named and kept), with an explanation of readout bias.
3. **Do they look random?** Bitmaps and Shannon entropy for both streams (pooled, and per-qubit mean for quantum), with the finite-sample estimator bias of about 1/(2N ln 2) explained.
4. **The attacker:** running accuracy for both attackers, P_guess with its 95% interval, H∞ at the point estimate and the conservative bound, the previous-shot attacker (Section 3.2), and the cross-checks.
5. **Appendix:** the bias attacker on `os.urandom` bits, the computational-hardness vs. physics distinction, and the limits from Section 3.2.

Charts use one shared matplotlib style, `pipeline/plotstyle.py`: classical is always the same warm colour and quantum always the same cool colour, and every chart title says "SYNTHETIC" when the data is.

The notebook is committed with outputs cleared (an `nbstripout` pre-commit hook enforces this). Tests execute it against the synthetic sample (with `nbclient`, through the `notebook` task) so it can't silently break.

## 9. Web app: presentation and audience

`ui/` is a Vite + React + TypeScript app with no UI component library; charts are hand-written SVG and canvas. At build time it imports `ui/src/data/demo.json` (Section 7.1), exported from one run, so neither view needs a network or a server. The one exception is the optional live run on the presenter's laptop (Section 6.4). Without it, everything works as before.

### 9.1 A hybrid of a presentation and an app

- **Presenter view** (the default). A slide deck shown on a projector: full-screen scenes on a fixed 16:9 stage, designed for 1920×1080 and identical in proportion at 1280×720. It opens on the first slide. Navigation with the arrow keys and a presentation clicker (PageUp/PageDown, Space), a subtle progress indicator, presenter notes toggled with N (hidden by default), fullscreen with F, and a large QR code overlay for latecomers toggled with Q (Q again or Escape closes it). A scene may have **steps**: "next" first reveals the scene's next step and only then moves on, and "back" from a scene's first step lands on the last step of the scene before. Some scenes contain interactive **panels** (Section 9.5).
- **Phone version** (the audience's view). A phone-first page designed for portrait phones (390×844) that offers **only the games** (Section 9.6): no slides, no presenter notes, no panels from the talk, no primitives page, and none of the presenter keys. It is the whole of the `build:web` build (Section 9.2), served at the site root, and the same screens open in the presenter builds with `?view=audience`, for rehearsals.

**Audience participation is in person.** People raise hands and call out guesses, and the presenter presses keys to reveal answers and results on the projector. There is no room, no real-time sync between devices, no audience vote counting, and no backend for the audience of any kind. The only server is the optional live server on the presenter's laptop (Section 6.4), which binds to that laptop alone, so phones never reach it.

**Phones use a separate static copy.** A QR code on screen points to a static hosted copy of the phone version (the `build:web` build). That copy is not connected to the presenter's app: it never follows the presenter's slide, sends nothing, and receives nothing. The UI never implies that phones are connected to the talk.

### 9.2 Running it

| Command | What it is |
|---|---|
| `npm run dev` | Local dev server for working on the UI. |
| `npm run preview` | Builds the production app into `ui/dist/` and serves it locally. **The primary way to present.** |
| `npm run build:demo` | Fallback: one self-contained `index.html` with all JS, CSS, fonts, and data inlined, written to the repo-level `demo/index.html` (committed). It opens by double-clicking, under `file://`, with the network off. |
| `npm run build:web` | The phone version only, as a static site in `ui/dist-web/` (gitignored) with its `index.html` at the root, so no `?view=audience` is needed. Its bundle contains no presenter code: no deck, slides, notes, presenter keys, talk panels, or primitives page. `npm run preview:web` serves it locally. |
| `python -m pipeline.tasks live-server` | **Optional, presenter's laptop only, human only.** Serves the last `npm run build` from `ui/dist/` with the live-run API (Section 6.4). Build with the hosted `VITE_AUDIENCE_URL` first, because the server doesn't rebuild. |

The tasks `ui-dev` and `ui-build` (Section 10) run the dev server and `build:demo`. Builds use relative URLs, and `ui/dist-web/` goes on any static host for phones; no server code is involved. The primitives page, which shows every reusable primitive rendered with real data from `demo.json`, opens with `#primitives` or `?primitives` (both work under `file://`) or the P key.

**The audience URL is a build-time setting.** `VITE_AUDIENCE_URL` (an environment variable when building, for example `VITE_AUDIENCE_URL=https://example.org/qrng/ npm run build:demo`) is the exact address phones should open: the hosted `build:web` site for the talk, or the laptop's local network address for a rehearsal. The opening slide, slide 8, and the Q overlay show it as a QR code, generated inside the app by a bundled library (never by an online service), and as short text without the `https://`. When the setting is empty or missing, those places show no QR code (the Q overlay says no address was set). Only `http:` and `https:` URLs are accepted.

### 9.3 Design rules

- **Tokens.** Colours, type, spacing, layout, and motion are CSS variables in one file, `ui/src/styles/tokens.css`. IBM Plex Sans for text and IBM Plex Mono for numbers and bits, self-hosted (no CDN), including the subsets needed for symbols such as ∞, ≈, ×, ±, →, and ₂. On the stage, body text is at least 24px at 1920×1080 and headline numbers at least 96px.
- **Colour.** An off-white background, near-black text, and one muted grey for secondary text. Exactly two semantic colours, classical (orange) and quantum (blue), with the same hues as `pipeline/plotstyle.py`. The exact hues are used for chart marks; darker versions of the same hues, meeting WCAG AA on the background, are used for text and big numbers. No gradients, glassmorphism, decorative shadows, emoji, or stock icons.
- **Motion.** Short transitions only (200–400 ms, ease-out), used to reveal results. `prefers-reduced-motion` turns them off.
- **Panels.** An interactive section of a slide is a `Panel`. Every control, in panels and in the phone games, is at least 44 CSS px in both dimensions, and nothing depends on hover.
- **Keys.** The deck's key handler ignores key events aimed at interactive elements (buttons, inputs, and anything with an interactive role), so Space or a digit pressed in a panel never also moves the deck. The deck's keys: arrows, PageUp/PageDown, Space, Home, End, Escape, N (notes), F (fullscreen), P (primitives page), and Q (QR code overlay). Panels on the current slide may listen for their own keys, which the deck never uses: 0 and 1 for a guess, R for a reveal, and M to switch machine (classical ↔ quantum); they ignore the same interactive targets and any key with a modifier. The phone version answers no keys of its own.
- **Scrolling.** The phone version uses ordinary page scrolling wherever content is taller than the screen: no fixed stage, no fixed-height page, and no touch handlers that block scrolling. Only the presenter's stage is fixed and does not scroll.
- **Copy.** Plain English throughout. Technical terms (min-entropy, Shannon entropy, Wilson interval, Mersenne Twister, z-score) appear only in small secondary text.
- **Responsive.** The presenter view is checked at 1920×1080 and 1280×720; the phone version at 390×844 with touch, including real touch scrolling.

### 9.4 The presentation scenes

The slides, in order. Every slide has presenter notes.

1. **Opening:** the title, plus a QR code and short URL inviting people to play along on their phones (Section 9.2). With no URL set, the title only.
2. **Why randomness matters:** where unpredictable numbers are used (passwords and keys, lotteries, simulations, games), in plain words.
3. **Meet the two machines:** the Machines panel, with the optional live run when the app is served by an armed live server (Section 6.4). The notes say what to do if the live run falls back, and that its job may still finish on IBM.
4. **Can you tell them apart?** The Tell-them-apart panel; a step reveals which is which, and a further step shows both Shannon gauges with the rule-chosen comparison phrase.
5. **Guess the next bit:** the Guess game, with a choice of machine.
6. **Enter the attacker:** the Guess game with the attacker row on; a step brings in the Attacker panel.
7. **Measuring unpredictability:** the Unpredictability panel.
8. **Your turn: play on your phone:** the QR code and short URL, large, while people play the phone games. With no URL set, the title and a line about the games only.
9. **Takeaway:** quantum computers are real, accessible today, and produce randomness guaranteed by physics. The presenter notes carry the honest caveat about secure classical generators (Section 4.7) and the cross-check results.
10. **Inside the quantum computer** (appendix, for questions): the Hardware panel. Its notes cover the flagged qubits and that they were kept.

Presenter notes are in a panel toggled with the N key and hidden by default. If `demo.json` says `synthetic: true`, a label reading "SYNTHETIC DATA: not from quantum hardware" stays on every screen of both views, every screen of the phone version included, and can't be dismissed.

### 9.5 Panels

Panels are the interactive parts of slides; the phone version does not use them. All numbers come from `demo.json`, apart from the display-only counts in Section 7.

- **Machines.** Classical and quantum side by side (stacked on phones). "Generate bits" streams bits from each stream's pool, with a speed control; the bitmaps fill in live, and the fraction of ones and Shannon entropy of the bits shown so far update as bits arrive. When a pool runs out, generation stops and says "End of the recorded bits"; bits are never repeated or wrapped. The real run's backend, job ID, date, and qubit count are shown and labelled as the actual run (or as sample data when synthetic).
  - **Live run** (only when served by an armed live server, Section 6.4). A "Run on real quantum hardware now" button. It is an ordinary button with no key of its own, so it can't clash with the deck's keys or M. Each stage is shown as it happens: sending, the job ID as soon as it exists, queued with the time elapsed, and running. When the run is done, the quantum machine switches to the fresh bits, labelled "Fresh from <backend>, <time>", with the live job's facts in place of the recorded run's. Both machines restart from their first bit and stream in step, the classical one from its pool as before. Streaming stops at the end of the fresh bits ("End of the fresh bits"). While fresh bits play, both pictures are sized to the bits received, not 128×128. The width is the largest divisor of the bit count no greater than its square root, and the height is the bit count divided by that width, so 2,000 bits give 40 × 50. When that shape would be more than 1.5 times taller than wide, the width is the square root rounded up, and the last row is left partly blank. Cells stay square, and the picture fits inside the same on-screen square as the normal picture. A small caption gives the dimensions ("40 × 50 bits"). The normal 128×128 picture is unchanged. Secondary text says a live run is small (its bit count, from the response), so its numbers are noisy, and that the headline numbers come from the full run. After 120 seconds without a result, the panel says "IBM's queue is busy; showing the run from <date>". After any failure (the job fails, or the server can't be reached), it says "The live run didn't finish; showing the run from <date>". In both cases it keeps the recorded run. Live bits are used only by this panel.
- **Tell them apart.** Two unlabelled bitmaps, in an order chosen at random for each session, and a reveal (the R key, a button, or the slide's next step). No vote counting.
- **Guess game.** Rounds of "guess the next bit" against a chosen machine. The presenter presses 0 or 1 (keys or large buttons) for the room's guess; the true bit is revealed and a running score shows. An optional attacker row shows what the attacker guessed each round and its score alongside the room's. Each session starts at a random offset in the pool that leaves room for at least 200 rounds, and the game stops at the end of the pool.
- **Attacker.** Choose a machine and launch. The observation phase is animated (624 numbers for classical, the training half for quantum), then the running-accuracy line replays with its 95% band. A toggle shows the cross-checks (each attacker on the other machine).
- **Hardware.** The backend's qubits from Qiskit's bundled device description, with the qubits used highlighted and coloured by bias and the flagged qubits marked. Tapping or clicking selects the qubit nearest the pointer and shows its P(1), readout error, and z-score. On phones the map can be zoomed and scrolled sideways so single qubits are easy to tap. Secondary text says flagged qubits were kept, not removed. If there is no device description (synthetic data), the panel says so.
- **Unpredictability.** The two min-entropy numbers with their intervals and conservative values, and the plain reading: "How many bits of genuine surprise each bit contains, for someone trying to predict it." The formula appears in small text.

### 9.6 The phone version

Screens, in order, each a normal scrolling page:

1. **Intro:** a one-line title ("Can you beat a quantum computer?"), one plain sentence saying one machine is an ordinary computer formula and the other a real IBM quantum computer (or, with synthetic data, sample data standing in for one), and two large buttons, one for each game.
2. **Spot the quantum machine:** five rounds. Each round shows two unlabelled 64×64 images, one from each machine (the spot images, Section 7.1), drawn in the same ink and in a random left/right order, and asks which came from the quantum computer. Tapping an image answers; the reveal names both. Every round uses a fresh pair, and no image is shown twice in a session (if all have been shown, the game says so). The end shows the score and the data-backed sentence: hard to tell apart by eye, followed by the rule-chosen `shannon_comparison` phrase.
3. **Beat the attacker:** the player picks a machine, then guesses the next bit with large 0 and 1 buttons for 20 rounds. After each guess it shows the true bit, whether the player was right, and what the attacker guessed. The end shows the player's count and the attacker's count on the same bits side by side, with no comparative word chosen in the UI, followed by the rule-chosen phrase about that attacker over all unseen bits, and an invitation to try the other machine. Rounds follow the pool rules of the Guess game (random start, never repeated, stops at the end of the pool).
4. **Closing:** one or two sentences of takeaway (quantum randomness is guaranteed by physics, and good classical generators are unpredictable in practice too, Section 4.7), with the real run's backend, job ID, and date in small text.

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
| `notebook [--run <id> \| --sample <name>]` | Executes the notebook into `data/scratch/`. | Anyone |
| `ui-dev` | Starts the Vite dev server (`npm run dev`). | Anyone |
| `ui-build` | Builds the single-file fallback `demo/index.html` from the current `demo.json` (`npm run build:demo`). The phone site is built with `npm run build:web` in `ui/`. | Anyone |
| `build-demo --run <id>` | Exports one run (`export --run`) and then runs `ui-build`. | Anyone |
| `check` | Runs ruff, mypy, pytest, and the UI lint and type check. | Anyone |
| `refresh` | Runs `collect-quantum`, `analyze`, and `build-demo` in one go. | **Human only** |
| `live-server [--port N] [--backend <name>]` | Serves `ui/dist/` with the live-run API on 127.0.0.1 (Section 6.4). It can submit real jobs. | **Human only** |

`setup-check`, `make-sample`, `collect-classical`, `collect-quantum`, `export`, `notebook`, `ui-dev`, `ui-build`, and `live-server` exist so far. The others are added in later tasks.

## 11. Engineering conventions

- **Platforms:** both machines are macOS, and the workflow must behave identically on both. Use `pathlib` for all paths and resolve them from the repo root (`pipeline/paths.py`), never from the current directory.
- **Python:** 3.11 or newer. Use a plain `python -m venv .venv` and `pip`. Exact pins are in `requirements.txt` (runtime) and `requirements-dev.txt` (tools, plus the package in editable mode); `pyproject.toml` holds compatible ranges and tool configuration.
- **Node:** both machines use the version in `.nvmrc` (26.3.0); `ui/package.json` requires 24 or newer. UI dependencies are pinned exactly in `ui/package.json`, with `ui/package-lock.json` committed. Install with `npm ci`. Playwright is a dev dependency used only by `ui/scripts/verify.mjs` for visual and offline checks; no run mode or task needs it. The one runtime dependency besides React is `qrcode-generator`, bundled into the build so the QR code needs no network. A few pure TypeScript modules (`ui/src/lib/stats.ts`, `ui/src/lib/pool.ts`) are also run directly by Node, using its built-in type stripping, from pytest (`tests/test_ui_stats.py`), so they use only erasable TypeScript syntax and import nothing from the browser.
- **Quality checks:** ruff for linting and formatting, mypy in strict mode, and pytest. Pre-commit runs detect-secrets, ruff, mypy, and basic hygiene hooks.
- **Tests never touch IBM Quantum.** Collector tests use a mocked `QiskitRuntimeService`; the Sampler is either mocked or the real client-side Sampler running locally on Aer (`qiskit-aer`, a dev dependency). They must cover refusal on a non-Open-Plan instance, refusal on low remaining allowance, the bit-order conversion, and that no CRN or token appears in output. A shared test fixture makes constructing a real `QiskitRuntimeService`, or a Sampler on anything but a local Aer simulator, fail the test at once. Live-server tests run the server in-process on a random 127.0.0.1 port with a mocked service. They cover arming refusals, the run cap, the stages and failures, `data/live/` isolation from export, and every security rule in Section 6.4. The UI verifier checks the live control in armed, unarmed, and unreachable states by mocking the API in the browser, and checks that the control is absent from the phone site, the single-file build, and plain preview.
- **Version control:** run folders, sample data, the notebook (outputs cleared), and `demo/index.html` are committed. `data/scratch/`, `data/live/`, `scratch/`, `.env*`, and virtualenvs are not.
