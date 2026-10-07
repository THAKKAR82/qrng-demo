// Types for demo.json. They mirror demo.schema.json and SCHEMA.md field for field;
// demo.ts assigns the imported JSON to DemoData, so `npm run typecheck` fails if the
// exported data and these types drift apart. Do not add fields here that the schema
// does not have.
//
// JSON imports widen literal types, so enums and bits are typed as string and number
// here; demo.ts checks their values at load time.

/** UTC time, `YYYY-MM-DDTHH:MM:SSZ`. */
export type UtcString = string

export interface Metadata {
  run_folder: string
  synthetic: boolean
  sample: boolean
  /** "ibm_quantum_hardware" or "synthetic". */
  source: string
  backend: string | null
  backend_num_qubits: number | null
  job_id: string | null
  date_utc: UtcString | null
  shots: number
  n_qubits: number
  qubits_selected_by_readout_error: boolean
  qubit_selection_method: string | null
  qubit_selection_candidates: number | null
  classical_generator: string
  classical_synthetic: boolean
}

export interface Bitmap {
  size: number
  /** `size` strings of `size` characters, each "0" or "1". */
  rows: string[]
  /** All its bits lie inside the attacker's training data. */
  within_training: boolean
}

/** Held-out bits, packed (see lib/pool.ts, which is the only reader). */
export interface Pool {
  start_bit: number
  n_bits: number
  /** Base64 of the bits packed 8 per byte, most significant bit first. */
  bits: string
  predictions: string
}

export interface Running {
  n_bits: number[]
  accuracy: number[]
  ci_low: number[]
  ci_high: number[]
}

export interface Attacker {
  name: string
  accuracy: number
  ci_low: number
  ci_high: number
  n_predicted: number
  n_training_bits: number
  min_entropy: number
  min_entropy_conservative: number
  min_entropy_high: number
  running: Running
}

export interface QubitResult {
  column: number
  physical_qubit: number | null
  readout_error: number | null
  p_one: number
  z: number
  flagged: boolean
  shannon_entropy: number
  attacker_accuracy: number
}

export interface BiasTests {
  z_threshold: number
  flagged_columns: number[]
  flagged_physical_qubits: (number | null)[]
  chi_square: number
  chi_square_dof: number
  chi_square_p: number
  mean_p_one: number
  mean_z: number
  mean_p: number
  across_qubits_t: number | null
  across_qubits_p: number | null
}

export interface QuantumStream {
  n_bits: number
  fraction_ones: number
  shannon_entropy: {
    pooled: number
    per_qubit_mean: number
    per_qubit_min: number
  }
  bias_summary: {
    mean_p_one: number
    mean_abs_bias: number
    worst: {
      column: number
      physical_qubit: number | null
      p_one: number
      abs_bias: number
    }
  }
  bias_tests: BiasTests
  qubits: QubitResult[]
  bitmap: Bitmap
  pool: Pool
  attacker: Attacker
}

export interface ClassicalStream {
  n_bits: number
  fraction_ones: number
  shannon_entropy: {
    pooled: number
  }
  bitmap: Bitmap
  pool: Pool
  attacker: Attacker
}

export interface CrossCheck {
  name: string
  accuracy: number
  ci_low: number
  ci_high: number
  n_predicted: number
  n_training_bits: number
  min_entropy: number
  consistent_with_half: boolean
  running: Running
}

export interface DeviceLayout {
  description: string
  device: string
  qiskit_ibm_runtime_version: string
  num_qubits: number
  /** Undirected couplings [a, b], a < b. */
  edges: number[][]
  /** [x, y] per qubit, in grid units. */
  coordinates: number[][]
}

/** Comparative phrases chosen by rule in pipeline/wording.py; shown verbatim. */
export interface Copy {
  shannon_comparison: string
  classical_attack: string
  quantum_attack: string
  unpredictability_comparison: string
  bias_note: string
}

export interface DemoData {
  schema_version: number
  generated_utc: UtcString
  metadata: Metadata
  quantum: QuantumStream
  classical: ClassicalStream
  cross_checks: {
    mt_on_quantum: CrossCheck
    bias_on_classical: CrossCheck
  }
  layout: DeviceLayout | null
  copy: Copy
}

/** The two sources. Every colour, label, and chart series is keyed by one of these. */
export type Source = 'classical' | 'quantum'
