"""Synthetic sample data (SPEC.md, Section 5.4). Always labelled synthetic.

The quantum-like bits are independent Bernoulli draws from NumPy with a fixed per-column
P(1) around 0.45 and a fixed seed. They are NOT from quantum hardware. The classical stream
is generated exactly as for a real run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pipeline import classical, runs
from pipeline.paths import SAMPLE_DIR

SAMPLE_NAME = "synthetic-v1"
SAMPLE_SEED = 20261005
SAMPLE_QUBITS = 100
SAMPLE_SHOTS = 2_000
P_ONE_CENTER = 0.45
P_ONE_HALF_WIDTH = 0.03

_GENERATED_FILES = (
    runs.QUANTUM_NPZ,
    runs.QUANTUM_JSON,
    runs.CLASSICAL_NPZ,
    runs.CLASSICAL_JSON,
    "results.json",
)


def synthetic_bits(
    shots: int, n_qubits: int, seed: int = SAMPLE_SEED
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.float64]]:
    """Return ``(bits, p_one)``: bits of shape ``(shots, n_qubits)`` and each column's P(1)."""
    rng = np.random.default_rng(seed)
    p_one = np.round(
        rng.uniform(P_ONE_CENTER - P_ONE_HALF_WIDTH, P_ONE_CENTER + P_ONE_HALF_WIDTH, n_qubits),
        4,
    )
    bits = (rng.random((shots, n_qubits)) < p_one).astype(np.uint8)
    return bits, p_one


def make_sample(
    name: str = SAMPLE_NAME,
    *,
    shots: int = SAMPLE_SHOTS,
    n_qubits: int = SAMPLE_QUBITS,
    sample_dir: Path = SAMPLE_DIR,
) -> Path:
    """(Re)generate ``data/sample/<name>/`` with synthetic quantum-like bits and classical data."""
    folder = sample_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    for filename in _GENERATED_FILES:
        (folder / filename).unlink(missing_ok=True)

    bits, p_one = synthetic_bits(shots, n_qubits)
    np.savez_compressed(folder / runs.QUANTUM_NPZ, bits=bits)

    meta: dict[str, Any] = {
        "schema_version": runs.SCHEMA_VERSION,
        "run_id": name,
        "created_utc": runs.iso_utc(runs.utc_now()),
        "source": "synthetic",
        "synthetic": True,
        "note": "SYNTHETIC DATA: not from quantum hardware. Independent Bernoulli bits from NumPy.",
        "generator": {
            "library": "numpy.random.default_rng",
            "seed": SAMPLE_SEED,
            "distribution": "independent Bernoulli per column",
            "p_one_range": [
                round(P_ONE_CENTER - P_ONE_HALF_WIDTH, 4),
                round(P_ONE_CENTER + P_ONE_HALF_WIDTH, 4),
            ],
        },
        "backend": None,
        "plan": None,
        "job": {"job_id": None, "shots": shots},
        "qubits": [
            {
                "column": column,
                "physical_qubit": "synthetic",
                "readout_error": None,
                "p_one": float(p),
            }
            for column, p in enumerate(p_one)
        ],
        "qubit_selection": {
            "used": False,
            "method": "synthetic",
            "candidates": None,
            "calibration_utc": None,
        },
        "bits": {
            "file": runs.QUANTUM_NPZ,
            "array": "bits",
            "dtype": "uint8",
            "shape": [shots, n_qubits],
            "columns": "logical qubit order",
        },
        "software": runs.software_versions(),
    }
    runs.write_json(folder / runs.QUANTUM_JSON, meta)
    classical.collect_for_folder(folder)
    return folder
