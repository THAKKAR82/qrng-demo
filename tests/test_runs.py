import json
from pathlib import Path

import numpy as np

from pipeline import runs
from pipeline.paths import SAMPLE_DIR
from pipeline.sample import SAMPLE_NAME


def test_load_run_reads_the_sample_as_stored() -> None:
    run = runs.load_run(SAMPLE_DIR / SAMPLE_NAME)
    assert run.synthetic
    assert run.bits.dtype == np.uint8
    assert run.bits.ndim == 2
    assert run.words.dtype == np.uint32
    assert run.bits.size <= run.words.size * 32
    # The sample uses no fake physical qubits and has no readout errors.
    assert run.physical_qubits() == [None] * run.bits.shape[1]
    assert run.readout_errors() == [None] * run.bits.shape[1]


def _write_run(folder: Path, q_meta: dict[str, object], c_meta: dict[str, object]) -> None:
    folder.mkdir()
    np.savez_compressed(folder / runs.QUANTUM_NPZ, bits=np.zeros((4, 2), dtype=np.uint8))
    np.savez_compressed(folder / runs.CLASSICAL_NPZ, words=np.zeros(1, dtype=np.uint32))
    (folder / runs.QUANTUM_JSON).write_text(json.dumps(q_meta))
    (folder / runs.CLASSICAL_JSON).write_text(json.dumps(c_meta))


def test_load_run_maps_qubits_by_column(tmp_path: Path) -> None:
    q_meta = {
        "synthetic": False,
        "qubits": [
            {"column": 1, "physical_qubit": 7, "readout_error": 0.01},
            {"column": 0, "physical_qubit": 3, "readout_error": None},
        ],
    }
    _write_run(tmp_path / "r", q_meta, {"synthetic": False})
    run = runs.load_run(tmp_path / "r")
    assert not run.synthetic
    assert run.physical_qubits() == [3, 7]
    assert run.readout_errors() == [None, 0.01]


def test_missing_synthetic_flag_counts_as_synthetic(tmp_path: Path) -> None:
    _write_run(tmp_path / "r", {"synthetic": False}, {})
    assert runs.load_run(tmp_path / "r").synthetic
