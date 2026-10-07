import json
import re
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pytest

from pipeline import classical, export, runs
from pipeline.attacker import BiasAttacker
from pipeline.paths import REPO_ROOT, RUNS_DIR, SAMPLE_DIR
from pipeline.tasks import main

SCHEMA_PATH = REPO_ROOT / "ui" / "src" / "data" / "demo.schema.json"
PLANTED_CRN = "crn:v1:bluemix:public:quantum-computing:us-east:a/0123456789abcdef:fedcba::"
PLANTED_TOKEN = "Zx9" + "q" * 40  # pragma: allowlist secret


def _make_run(
    folder: Path,
    *,
    shots: int = 400,
    n_qubits: int = 100,
    with_classical: bool = True,
    seed: int = 0,
) -> np.ndarray:
    """A run folder shaped like a real one, with secret-like strings planted in metadata
    that export must never copy. Column 3 is heavily biased so it gets flagged."""
    folder.mkdir(parents=True)
    rng = np.random.default_rng(seed)
    bits = (rng.random((shots, n_qubits)) < 0.47).astype(np.uint8)
    bits[:, 3] = (rng.random(shots) < 0.2).astype(np.uint8)
    np.savez_compressed(folder / runs.QUANTUM_NPZ, bits=bits)
    meta: dict[str, Any] = {
        "schema_version": 1,
        "run_id": folder.name,
        "created_utc": "2026-10-06T01:35:06Z",
        "source": "ibm_quantum_hardware",
        "synthetic": False,
        "recovered": False,
        "recovery": None,
        "backend": {"name": "ibm_testbed", "num_qubits": 156},
        "plan": {"plan": "open", "pricing_type": "free", "instance": PLANTED_CRN},
        "account": "qrng-open",
        "job": {
            "job_id": "d0testjob0000000000",
            "shots": shots,
            "submitted_utc": "2026-10-06T01:34:54Z",
            "completed_utc": "2026-10-06T01:35:01Z",
        },
        "qubits": [
            {"column": j, "physical_qubit": 2 * j, "readout_error": 0.001 * (j + 1)}
            for j in range(n_qubits)
        ],
        "qubit_selection": {
            "used": True,
            "method": "lowest_readout_error",
            "candidates": 156,
            "calibration_utc": "2026-10-06T01:12:29Z",
        },
        "sampler": {"options": {"token": PLANTED_TOKEN}},
        "software": {"python": "3.13.9", "path": "/Users/someone/.qiskit/qiskit-ibm.json"},
    }
    runs.write_json(folder / runs.QUANTUM_JSON, meta)
    if with_classical:
        classical.collect_for_folder(folder)
    return bits


def _secret_like(text: str) -> list[str]:
    """Secret-like strings in a serialized export. The pools' packed bits are swapped for a
    placeholder first (base64 bits look token-like by chance); ``scannable_text`` only does
    that after checking they are plain base64 holding exactly the pool's bits."""
    text = export.scannable_text(json.loads(text))
    patterns = [
        r"crn:",
        r"qrng-open",
        r"\.qiskit",
        r"/Users/",
        r"/home/",
        r"/private/",
        r"/var/folders",
        r"~/",
        r"[A-Za-z]:\\",
        r"(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{32,}",
        re.escape(str(REPO_ROOT)),
        re.escape(str(Path.home())),
    ]
    return [p for p in patterns if re.search(p, text)]


def _validate(path: Path) -> dict[str, Any]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    demo = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(demo)
    return dict(demo)


# --- Picking the source ----------------------------------------------------------------------


def test_latest_run_is_the_newest_complete_run(tmp_path: Path) -> None:
    _make_run(tmp_path / "2026-10-06T013454Z_ibm_fez")
    _make_run(tmp_path / "2026-11-01T090000Z_ibm_torino")
    _make_run(tmp_path / "2026-10-31T235959Z_ibm_zzz")
    _make_run(tmp_path / "2026-12-01T000000Z_ibm_fez", with_classical=False)  # incomplete
    (tmp_path / "zz-notes").mkdir()
    (tmp_path / ".gitkeep").touch()
    latest = export.find_latest_run(tmp_path)
    assert latest is not None
    assert latest.name == "2026-11-01T090000Z_ibm_torino"


def test_latest_run_is_none_without_runs(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    assert export.find_latest_run(tmp_path) is None


def test_resolve_source_falls_back_to_sample(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    folder, is_sample = export.resolve_source(runs_dir=runs_dir, sample_dir=SAMPLE_DIR)
    assert folder == SAMPLE_DIR / "synthetic-v1"
    assert is_sample is True


def test_resolve_source_explicit_run(tmp_path: Path) -> None:
    _make_run(tmp_path / "2026-10-06T013454Z_ibm_fez")
    _make_run(tmp_path / "2026-11-01T090000Z_ibm_torino")
    folder, is_sample = export.resolve_source(
        run="2026-10-06T013454Z_ibm_fez", runs_dir=tmp_path, sample_dir=SAMPLE_DIR
    )
    assert folder.name == "2026-10-06T013454Z_ibm_fez"
    assert is_sample is False


@pytest.mark.parametrize("name", ["missing", "../sample/synthetic-v1", "/etc"])
def test_resolve_source_rejects_unknown_or_escaping_runs(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        export.resolve_source(run=name, runs_dir=tmp_path, sample_dir=SAMPLE_DIR)


# --- Output ----------------------------------------------------------------------------------


def test_export_writes_valid_demo_without_secrets(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "2026-11-01T090000Z_ibm_testbed"
    bits = _make_run(run)
    out = tmp_path / "out" / "demo.json"
    export.write_demo(run, out, is_sample=False)

    text = out.read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) < 1_000_000
    assert _secret_like(text) == []
    assert str(tmp_path) not in text
    assert "/" + "Users" not in text

    demo = _validate(out)
    meta = demo["metadata"]
    assert meta["run_folder"] == "2026-11-01T090000Z_ibm_testbed"
    assert meta["synthetic"] is False
    assert meta["sample"] is False
    assert meta["backend"] == "ibm_testbed"
    assert meta["job_id"] == "d0testjob0000000000"
    assert meta["n_qubits"] == 100
    assert meta["qubits_selected_by_readout_error"] is True

    q = demo["quantum"]
    assert len(q["bitmap"]["rows"]) == 128
    assert all(len(row) == 128 for row in q["bitmap"]["rows"])
    assert "".join(q["bitmap"]["rows"][:2]) == "".join(map(str, bits.reshape(-1)[:256]))
    assert len(demo["classical"]["bitmap"]["rows"]) == 128

    # The pools are the first held-out bits, right after the attackers' training data,
    # with the attackers' predictions for exactly those bits.
    q_pool = q["pool"]
    assert q_pool["start_bit"] == 200 * 100 == q["attacker"]["n_training_bits"]
    assert q_pool["n_bits"] == 20_000
    q_pool_bits = export.unpack_bits(q_pool["bits"], q_pool["n_bits"])
    assert q_pool_bits.tolist() == bits[200:].reshape(-1)[:20_000].tolist()
    majority = (bits[:200].mean(axis=0) > 0.5).astype(np.uint8)
    q_predictions = export.unpack_bits(q_pool["predictions"], q_pool["n_bits"])
    assert q_predictions.tolist() == np.tile(majority, 200).tolist()

    c = demo["classical"]
    words = np.load(run / runs.CLASSICAL_NPZ)["words"]
    c_stream = classical.words_to_bits(words)
    c_pool = c["pool"]
    assert c_pool["start_bit"] == 624 * 32 == c["attacker"]["n_training_bits"]
    assert c_pool["n_bits"] == 20_000
    c_pool_bits = export.unpack_bits(c_pool["bits"], c_pool["n_bits"])
    assert c_pool_bits.tolist() == c_stream[624 * 32 :][:20_000].tolist()
    # The state-recovery attacker predicts every held-out classical bit.
    assert export.unpack_bits(c_pool["predictions"], 20_000).tolist() == c_pool_bits.tolist()

    # Bitmaps are inside the training data here (16,384 <= 20,000 and 19,968 bits).
    assert q["bitmap"]["within_training"] is True
    assert c["bitmap"]["within_training"] is True

    # Running accuracy carries its interval at every point.
    for attacker in (q["attacker"], c["attacker"]):
        running = attacker["running"]
        assert len(running["ci_low"]) == len(running["ci_high"]) == len(running["n_bits"])
        assert all(
            lo <= a <= hi
            for lo, a, hi in zip(
                running["ci_low"], running["accuracy"], running["ci_high"], strict=True
            )
        )
        assert attacker["min_entropy_conservative"] <= attacker["min_entropy"]
        assert attacker["min_entropy"] <= attacker["min_entropy_high"]

    # No bundled description for a made-up backend.
    assert demo["layout"] is None
    assert set(demo["copy"]) == {
        "shannon_comparison",
        "classical_attack",
        "quantum_attack",
        "unpredictability_comparison",
        "bias_note",
    }
    assert demo["copy"]["classical_attack"] == (
        "The attacker predicted every classical bit correctly."
    )

    # The biased qubit is flagged and reported, not dropped.
    assert len(q["qubits"]) == 100
    assert 3 in q["bias_tests"]["flagged_columns"]
    assert q["qubits"][3]["flagged"] is True
    assert q["qubits"][3]["p_one"] == pytest.approx(bits[:, 3].mean(), abs=1e-4)
    assert q["bias_summary"]["worst"]["column"] == 3

    # Fairness cross-checks: each attacker against the other stream.
    cross = demo["cross_checks"]
    assert cross["mt_on_quantum"]["n_predicted"] == (40_000 // 32 - 624) * 32
    assert cross["bias_on_classical"]["n_predicted"] == 200 * 100
    for check in cross.values():
        assert len(check["running"]["n_bits"]) == len(check["running"]["ci_low"])
        # The classical stream is freshly seeded, so a 95% CI misses 0.5 one time in 20;
        # check the flag against its own CI, and the accuracy against a wide band.
        assert check["consistent_with_half"] is (check["ci_low"] <= 0.5 <= check["ci_high"])
        assert check["accuracy"] == pytest.approx(0.5, abs=0.05)


def test_export_of_sample_is_labelled_synthetic(tmp_path: Path) -> None:
    out = tmp_path / "demo.json"
    export.write_demo(SAMPLE_DIR / "synthetic-v1", out, is_sample=True)
    demo = _validate(out)
    assert demo["metadata"]["synthetic"] is True
    assert demo["metadata"]["sample"] is True
    assert demo["metadata"]["backend"] is None
    assert demo["metadata"]["job_id"] is None
    assert demo["quantum"]["qubits"][0]["physical_qubit"] is None
    assert demo["layout"] is None
    assert _secret_like(out.read_text(encoding="utf-8")) == []


def test_export_of_ibm_fez_run_includes_bundled_layout(tmp_path: Path) -> None:
    run = tmp_path / "2026-11-01T090000Z_ibm_fez"
    _make_run(run)
    meta = runs.read_json(run / runs.QUANTUM_JSON)
    meta["backend"]["name"] = "ibm_fez"
    runs.write_json(run / runs.QUANTUM_JSON, meta)
    out = tmp_path / "demo.json"
    export.write_demo(run, out, is_sample=False)
    layout = _validate(out)["layout"]
    assert layout["description"] == "Qiskit's bundled device description"
    assert layout["device"] == "FakeFez"
    assert layout["num_qubits"] == 156
    assert len(layout["coordinates"]) == 156


def test_pool_refuses_training_bits() -> None:
    bits = np.zeros((40, 10), dtype=np.uint8)
    result = BiasAttacker().attack(bits)
    with pytest.raises(ValueError, match="training"):
        export._pool(bits.reshape(-1), result, result.n_training_bits - 1)


def test_pack_bits_round_trip_and_bit_order() -> None:
    assert export.pack_bits([1, 0, 0, 0, 0, 0, 0, 1, 1]) == "gYA="  # 0x81, 0x80
    rng = np.random.default_rng(1)
    bits = rng.integers(0, 2, 20_003).astype(np.uint8)
    assert export.unpack_bits(export.pack_bits(bits), bits.size).tolist() == bits.tolist()


def test_scannable_text_rejects_non_base64_pool_fields(tmp_path: Path) -> None:
    run = tmp_path / "2026-11-01T090000Z_ibm_testbed"
    _make_run(run)
    demo = export.build_demo(run, is_sample=False)
    demo["quantum"]["pool"]["bits"] = PLANTED_CRN
    with pytest.raises(ValueError, match="base64"):
        export.scannable_text(demo)
    demo = export.build_demo(run, is_sample=False)
    demo["quantum"]["pool"]["bits"] = demo["quantum"]["pool"]["bits"] + "AAAA"
    with pytest.raises(ValueError, match="bits"):
        export.scannable_text(demo)


def test_export_of_committed_real_run_validates(tmp_path: Path) -> None:
    latest = export.find_latest_run(RUNS_DIR)
    if latest is None:
        pytest.skip("no committed real run")
    out = tmp_path / "demo.json"
    export.write_demo(latest, out, is_sample=False)
    demo = _validate(out)
    assert demo["metadata"]["synthetic"] is False
    assert demo["classical"]["attacker"]["accuracy"] == 1.0
    assert demo["classical"]["attacker"]["min_entropy"] == 0.0
    assert demo["layout"] is not None
    # Every pool has room for at least 200 guessing rounds after any start offset.
    assert demo["quantum"]["pool"]["n_bits"] >= 400
    assert demo["classical"]["pool"]["n_bits"] >= 400
    assert _secret_like(out.read_text(encoding="utf-8")) == []
    assert out.stat().st_size < 1_000_000


def test_write_demo_refuses_secret_like_output(tmp_path: Path) -> None:
    run = tmp_path / "2026-11-01T090000Z_ibm_testbed"
    _make_run(run)
    meta = runs.read_json(run / runs.QUANTUM_JSON)
    meta["job"]["job_id"] = PLANTED_CRN  # a field export does copy
    runs.write_json(run / runs.QUANTUM_JSON, meta)
    out = tmp_path / "demo.json"
    with pytest.raises(ValueError, match="secret"):
        export.write_demo(run, out, is_sample=False)
    assert not out.exists()


def test_export_cli_uses_latest_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    _make_run(runs_dir / "2026-10-06T013454Z_ibm_fez")
    _make_run(runs_dir / "2026-11-01T090000Z_ibm_torino")
    out = tmp_path / "demo.json"
    monkeypatch.setattr(export, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(export, "DEMO_JSON", out)
    assert main(["export"]) == 0
    assert _validate(out)["metadata"]["run_folder"] == "2026-11-01T090000Z_ibm_torino"
    assert main(["export", "--run", "2026-10-06T013454Z_ibm_fez"]) == 0
    assert _validate(out)["metadata"]["run_folder"] == "2026-10-06T013454Z_ibm_fez"
    assert main(["export", "--run", "nope"]) == 1
