# `demo.json` schema

`demo.json` is the only data file the UI imports. It is written by

```sh
python -m pipeline.tasks export                 # latest run in data/runs/, else the sample
python -m pipeline.tasks export --run <run_id>  # a specific run
python -m pipeline.tasks export --sample <name> # a folder under data/sample/
```

The machine-readable schema is [`demo.schema.json`](demo.schema.json) (JSON Schema 2020-12). `export` validates against it before writing, and the tests validate it again. Every object is closed (`additionalProperties: false`), so a new field needs a schema change first. See SPEC.md, Section 7.1.

**Guarantees:** under 1 MB; no credentials, CRNs, account or instance names, or local file paths. Do not hand-edit the file. Every on-screen number must come from it (SPEC.md, Section 4).

## Conventions

- Probabilities and entropies are numbers in [0, 1]. Entropies are in bits per bit.
- Floats are rounded to 6 significant digits.
- Times are UTC strings in the form `YYYY-MM-DDTHH:MM:SSZ`.
- `null` means "not applicable or unknown", for example the backend of synthetic data.
- **Columns** are logical qubits (indices into the bit array). **Physical qubits** are hardware qubit numbers, `null` for synthetic data.
- The quantum stream is flattened shot-major: all qubits of shot 0, then all qubits of shot 1, and so on. Classical words are unpacked most significant bit first.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | `1` | Bumped on breaking changes. |
| `generated_utc` | time | When `export` ran. |
| `metadata` | object | Where the data came from (below). |
| `quantum` | object | Quantum stream results (below). |
| `classical` | object | Classical (MT19937) stream results (below). |
| `cross_checks` | object | Each attacker run against the other stream (below). |

## `metadata`

| Field | Type | Meaning |
|---|---|---|
| `run_folder` | string | Folder name, for example `2026-10-06T013454Z_ibm_fez` or `synthetic-v1`. Never a path. |
| `synthetic` | bool | `true` if either stream is synthetic. **The UI must show the SYNTHETIC banner when this is `true`.** |
| `sample` | bool | `true` if exported from `data/sample/`. |
| `source` | `"ibm_quantum_hardware"` \| `"synthetic"` | |
| `backend` | string \| null | IBM backend name. |
| `backend_num_qubits` | int \| null | Size of the backend. |
| `job_id` | string \| null | IBM Quantum job ID. |
| `date_utc` | time \| null | Job completion time (real runs) or creation time (samples). |
| `shots` | int | Shots in the quantum job. |
| `n_qubits` | int | Qubits measured per shot. |
| `qubits_selected_by_readout_error` | bool | Whether qubits were picked by lowest readout error. If `true`, say so on screen (SPEC.md, Section 4.5). |
| `qubit_selection_method` | string \| null | `lowest_readout_error`, `first_n`, `explicit`, or `unknown_recovered`. |
| `qubit_selection_candidates` | int \| null | How many qubits the selection chose from. |
| `classical_generator` | string | `random.Random (MT19937)`. |
| `classical_synthetic` | bool | Whether `classical.json` is marked synthetic. |

## `quantum`

| Field | Type | Meaning |
|---|---|---|
| `n_bits` | int | Total quantum bits (`shots × n_qubits`). |
| `fraction_ones` | probability | Pooled fraction of ones. |
| `shannon_entropy.pooled` | bits | h(p̂) over all bits pooled. Pooling hides opposite biases. |
| `shannon_entropy.per_qubit_mean` | bits | Mean of the per-qubit h(p̂). This is the honest figure. |
| `shannon_entropy.per_qubit_min` | bits | Lowest per-qubit h(p̂). |
| `bias_summary.mean_p_one` | probability | Mean of the per-qubit P(1). |
| `bias_summary.mean_abs_bias` | number | Mean of \|P(1) − 0.5\| across qubits. |
| `bias_summary.worst` | object | The qubit with the largest \|P(1) − 0.5\|: `column`, `physical_qubit`, `p_one`, `abs_bias`. |
| `bias_tests` | object | See below. |
| `qubits` | array | One entry per column, **every qubit included** (see below). |
| `bitmap` | bitmap | First 16,384 bits of the stream. |
| `next_bits` | next bits | First 200 held-out bits. |
| `attacker` | attacker | The per-qubit bias attacker. |

### `quantum.bias_tests`

| Field | Meaning |
|---|---|
| `z_threshold` | 3. |
| `flagged_columns`, `flagged_physical_qubits` | Qubits with \|z\| > `z_threshold`. They are reported only, never removed. |
| `chi_square`, `chi_square_dof`, `chi_square_p` | Do the per-qubit P(1) values spread more than shot noise alone predicts? A small p means real qubit-to-qubit differences. |
| `mean_p_one`, `mean_z`, `mean_p` | Overall mean P(1) against 0.5 as a pooled binomial z-test (assumes every qubit shares one P(1)). |
| `across_qubits_t`, `across_qubits_p` | The same question as a one-sample t-test on the per-qubit P(1) values (no shared-P(1) assumption). `null` if undefined. |

### `quantum.qubits[]`

| Field | Meaning |
|---|---|
| `column` | Logical qubit / column index. |
| `physical_qubit` | Hardware qubit, or `null` for synthetic data. |
| `readout_error` | Readout error at selection time, or `null`. |
| `p_one` | P(1) over all shots. |
| `z` | (P(1) − 0.5) / √(0.25 / shots). |
| `flagged` | \|z\| > `bias_tests.z_threshold`. |
| `shannon_entropy` | h(P(1)) for this qubit. |
| `attacker_accuracy` | Bias attacker's accuracy on this qubit's held-out shots. |

## `classical`

| Field | Type | Meaning |
|---|---|---|
| `n_bits` | int | Total classical bits. |
| `fraction_ones` | probability | Fraction of ones. |
| `shannon_entropy.pooled` | bits | h(p̂). |
| `bitmap` | bitmap | First 16,384 bits of the stream. |
| `next_bits` | next bits | First 200 held-out bits (right after the 624 observed words). |
| `attacker` | attacker | The Mersenne Twister state-recovery attacker. |

## `cross_checks`

Fairness checks (SPEC.md, Section 3.1). Both should score about 0.5, showing neither attacker was tuned to make one source look bad. For the presenter notes.

| Field | Meaning |
|---|---|
| `mt_on_quantum` | The MT state-recovery attacker on the quantum bits, packed into 32-bit words most significant bit first, in shot-major order. |
| `bias_on_classical` | The bias attacker on the classical bits, reshaped to the quantum `(shots, qubits)` shape and split in half by shots. |

Each has `name`, `accuracy`, `ci_low`, `ci_high` (95% Wilson), `n_predicted`, `min_entropy`, and `consistent_with_half` (`true` if 0.5 lies inside the interval). With a 95% interval, a fair attacker misses 0.5 about one time in twenty, so a `false` here is not on its own evidence of a problem.

## Shared shapes

**bitmap:** `size` (always 128) and `rows`, 128 strings of 128 characters each, `"0"` or `"1"`. Row `r`, character `c` is bit `128·r + c` of the stream. Draw 1 as white and 0 as black.

**next bits:** `start_bit` (index into the flattened stream of the first bit), `bits` (200 values, 0 or 1), and `attacker_predictions` (the attacker's guess for each of those 200 bits). These bits come right after the attacker's training data, so the attacker never saw them.

**attacker:**

| Field | Meaning |
|---|---|
| `name` | Attacker name. |
| `accuracy` | P_guess: fraction of held-out bits predicted correctly. |
| `ci_low`, `ci_high` | 95% Wilson interval for `accuracy`. |
| `n_predicted` | Held-out bits predicted. |
| `n_training_bits` | Bits the attacker saw first. |
| `min_entropy` | H∞ = −log2(max(a, 1 − a)) for accuracy a. A reliably wrong attacker is as good as a reliably right one (flip every guess), so accuracy 0 and 1 both give 0 bits and 0.5 gives 1 bit. |
| `min_entropy_conservative` | H∞ at whichever of `ci_low` and `ci_high` gives the larger max(a, 1 − a), i.e. the lower H∞. |
| `running.n_bits`, `running.accuracy` | Accuracy over the first `n_bits[i]` predictions, for a convergence chart. At most 500 points, including the first and last prediction. |
