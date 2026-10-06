from pathlib import Path

import numpy as np

from pipeline import runs, sample


def test_make_sample_layout_and_labels(tmp_path: Path) -> None:
    folder = sample.make_sample("s", shots=400, n_qubits=10, sample_dir=tmp_path)
    assert folder == tmp_path / "s"

    with np.load(folder / runs.QUANTUM_NPZ) as data:
        bits = data["bits"]
    assert bits.dtype == np.uint8
    assert bits.shape == (400, 10)
    assert set(np.unique(bits).tolist()) <= {0, 1}

    quantum_meta = runs.read_json(folder / runs.QUANTUM_JSON)
    assert quantum_meta["synthetic"] is True
    assert quantum_meta["source"] == "synthetic"
    assert all(q["physical_qubit"] == "synthetic" for q in quantum_meta["qubits"])
    assert len(quantum_meta["qubits"]) == 10

    classical_meta = runs.read_json(folder / runs.CLASSICAL_JSON)
    assert classical_meta["synthetic"] is True
    assert classical_meta["matched_bits"] == 4000
    assert classical_meta["seed_stored"] is False


def test_synthetic_bits_are_deterministic_and_biased() -> None:
    bits_a, p_a = sample.synthetic_bits(20_000, 5)
    bits_b, p_b = sample.synthetic_bits(20_000, 5)
    assert np.array_equal(bits_a, bits_b)
    assert np.array_equal(p_a, p_b)
    assert np.all((p_a >= 0.42) & (p_a <= 0.48))
    assert np.allclose(bits_a.mean(axis=0), p_a, atol=0.015)


def test_make_sample_regenerates_in_place(tmp_path: Path) -> None:
    folder = sample.make_sample("s", shots=10, n_qubits=3, sample_dir=tmp_path)
    (folder / "results.json").write_text("{}")
    sample.make_sample("s", shots=10, n_qubits=3, sample_dir=tmp_path)
    assert not (folder / "results.json").exists()
