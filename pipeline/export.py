"""Export one run (or the synthetic sample) to ``ui/src/data/demo.json`` for the UI.

The output follows ``ui/src/data/demo.schema.json`` (documented in ``SCHEMA.md``) and is
validated against it before anything is written. Fields are copied from the run's
metadata by an explicit allow-list, never wholesale, and the serialized output is checked
for secret-like strings and local paths. See SPEC.md, Section 7.1.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import numpy.typing as npt

from pipeline import runs
from pipeline.analysis import analyze_bias, binary_entropy, bitmap, shannon_entropy_per_bit
from pipeline.attacker import AttackResult, BiasAttacker, MersenneTwisterAttacker
from pipeline.classical import words_to_bits
from pipeline.paths import REPO_ROOT, RUNS_DIR, SAMPLE_DIR, UI_DATA_DIR
from pipeline.sample import SAMPLE_NAME

DEMO_JSON = UI_DATA_DIR / "demo.json"
SCHEMA_JSON = UI_DATA_DIR / "demo.schema.json"
DEMO_SCHEMA_VERSION = 1
MAX_BYTES = 1_000_000
BITMAP_SIZE = 128
NEXT_BITS = 200

RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z_[A-Za-z0-9_\-]+$")
_REQUIRED_FILES = (runs.QUANTUM_NPZ, runs.QUANTUM_JSON, runs.CLASSICAL_NPZ, runs.CLASSICAL_JSON)

# Anything matching these must never reach the UI bundle.
_SECRET_PATTERNS = [
    re.compile(r"crn:", re.IGNORECASE),
    re.compile(r"qrng-open"),
    re.compile(r"\.qiskit"),
    re.compile(r"(?:/Users/|/home/|/private/|/var/folders|~/)"),
    re.compile(r"[A-Za-z]:\\"),
    # Long token-like strings (API keys). Requiring both a letter and a digit skips the
    # 0/1 bitmap rows and long snake_case key names.
    re.compile(r"(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{32,}"),
]


def _is_complete(folder: Path) -> bool:
    return folder.is_dir() and all((folder / name).is_file() for name in _REQUIRED_FILES)


def find_latest_run(runs_dir: Path | None = None) -> Path | None:
    """The newest complete run folder. Run ids start with a UTC timestamp, so the
    lexicographically greatest name is the newest."""
    base = RUNS_DIR if runs_dir is None else runs_dir
    if not base.is_dir():
        return None
    candidates = [p for p in base.iterdir() if RUN_ID_RE.match(p.name) and _is_complete(p)]
    return max(candidates, key=lambda p: p.name, default=None)


def _child(base: Path, name: str) -> Path:
    """``base / name`` for a plain folder name; rejects anything that could escape ``base``."""
    if Path(name).name != name or name in {"", ".", ".."} or name.startswith("."):
        raise ValueError(f"not a plain folder name: {name!r}")
    folder = base / name
    if not _is_complete(folder):
        raise ValueError(f"{name} is not a complete run folder")
    return folder


def resolve_source(
    run: str | None = None,
    sample: str | None = None,
    *,
    runs_dir: Path | None = None,
    sample_dir: Path | None = None,
) -> tuple[Path, bool]:
    """Pick the folder to export and say whether it is sample data.

    ``run`` or ``sample`` if given; otherwise the latest run, falling back to the sample.
    """
    runs_base = RUNS_DIR if runs_dir is None else runs_dir
    sample_base = SAMPLE_DIR if sample_dir is None else sample_dir
    if run is not None:
        return _child(runs_base, run), False
    if sample is not None:
        return _child(sample_base, sample), True
    latest = find_latest_run(runs_base)
    if latest is not None:
        return latest, False
    return _child(sample_base, SAMPLE_NAME), True


def _num(value: float) -> float | None:
    """Round to 6 significant digits to keep the file small; NaN becomes null."""
    if math.isnan(value):
        return None
    return float(f"{value:.6g}") + 0.0


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _rows(image: npt.NDArray[np.uint8]) -> list[str]:
    return ["".join("1" if b else "0" for b in row) for row in image]


def _attacker(result: AttackResult) -> dict[str, Any]:
    return {
        "name": result.attacker,
        "accuracy": _num(result.accuracy),
        "ci_low": _num(result.ci_low),
        "ci_high": _num(result.ci_high),
        "n_predicted": result.n_predicted,
        "n_training_bits": result.n_training_bits,
        "min_entropy": _num(result.min_entropy),
        "min_entropy_conservative": _num(result.min_entropy_conservative),
        "running": {
            "n_bits": [int(i) for i in result.running_index],
            "accuracy": [_num(float(a)) for a in result.running_accuracy],
        },
    }


def _next_bits(
    stream: npt.NDArray[np.uint8], result: AttackResult, start_bit: int
) -> dict[str, Any]:
    """The first held-out bits (right after the attacker's training data), with the
    attacker's prediction for each, for the audience guessing game."""
    return {
        "start_bit": start_bit,
        "bits": [int(b) for b in stream[start_bit : start_bit + NEXT_BITS]],
        "attacker_predictions": [int(b) for b in result.predictions[:NEXT_BITS]],
    }


def build_demo(folder: Path, *, is_sample: bool) -> dict[str, Any]:
    q_meta = runs.read_json(folder / runs.QUANTUM_JSON)
    c_meta = runs.read_json(folder / runs.CLASSICAL_JSON)
    with np.load(folder / runs.QUANTUM_NPZ) as data:
        q_bits = np.asarray(data["bits"], dtype=np.uint8)
    with np.load(folder / runs.CLASSICAL_NPZ) as data:
        words = np.asarray(data["words"], dtype=np.uint32)
    q_stream = q_bits.reshape(-1)
    c_stream = words_to_bits(words)
    shots, n_qubits = q_bits.shape

    synthetic = bool(q_meta.get("synthetic", True)) or bool(c_meta.get("synthetic", True))
    backend = q_meta.get("backend") or {}
    job = q_meta.get("job") or {}
    selection = q_meta.get("qubit_selection") or {}
    qubit_meta = {int(q["column"]): q for q in q_meta.get("qubits", [])}
    physical = [_int_or_none(qubit_meta.get(j, {}).get("physical_qubit")) for j in range(n_qubits)]

    bias = analyze_bias(q_bits)
    bias_attacker = BiasAttacker()
    q_attack = bias_attacker.attack(q_bits)
    c_attack = MersenneTwisterAttacker().attack(words)
    assert q_attack.per_qubit_accuracy is not None

    per_qubit_entropy = [binary_entropy(float(p)) for p in bias.p_one]
    abs_bias = np.abs(bias.p_one - 0.5)
    worst = int(np.argmax(abs_bias))

    qubits = []
    for j in range(n_qubits):
        readout = qubit_meta.get(j, {}).get("readout_error")
        qubits.append(
            {
                "column": j,
                "physical_qubit": physical[j],
                "readout_error": _num(float(readout)) if isinstance(readout, float) else None,
                "p_one": _num(float(bias.p_one[j])),
                "z": _num(float(bias.z_scores[j])),
                "flagged": j in bias.flagged,
                "shannon_entropy": _num(per_qubit_entropy[j]),
                "attacker_accuracy": _num(float(q_attack.per_qubit_accuracy[j])),
            }
        )

    return {
        "schema_version": DEMO_SCHEMA_VERSION,
        "generated_utc": runs.iso_utc(runs.utc_now()),
        "metadata": {
            "run_folder": folder.name,
            "synthetic": synthetic,
            "sample": is_sample,
            "source": "synthetic" if synthetic else "ibm_quantum_hardware",
            "backend": backend.get("name"),
            "backend_num_qubits": _int_or_none(backend.get("num_qubits")),
            "job_id": job.get("job_id"),
            "date_utc": job.get("completed_utc") or q_meta.get("created_utc"),
            "shots": shots,
            "n_qubits": n_qubits,
            "qubits_selected_by_readout_error": bool(selection.get("used", False)),
            "qubit_selection_method": selection.get("method"),
            "qubit_selection_candidates": _int_or_none(selection.get("candidates")),
            "classical_generator": str(c_meta.get("generator", "")),
            "classical_synthetic": bool(c_meta.get("synthetic", True)),
        },
        "quantum": {
            "n_bits": int(q_stream.size),
            "fraction_ones": _num(float(q_stream.mean())),
            "shannon_entropy": {
                "pooled": _num(shannon_entropy_per_bit(q_stream)),
                "per_qubit_mean": _num(float(np.mean(per_qubit_entropy))),
                "per_qubit_min": _num(float(np.min(per_qubit_entropy))),
            },
            "bias_summary": {
                "mean_p_one": _num(bias.mean_p_one),
                "mean_abs_bias": _num(float(abs_bias.mean())),
                "worst": {
                    "column": worst,
                    "physical_qubit": physical[worst],
                    "p_one": _num(float(bias.p_one[worst])),
                    "abs_bias": _num(float(abs_bias[worst])),
                },
            },
            "bias_tests": {
                "z_threshold": bias.z_threshold,
                "flagged_columns": bias.flagged,
                "flagged_physical_qubits": [physical[j] for j in bias.flagged],
                "chi_square": _num(bias.chi_square),
                "chi_square_dof": bias.chi_square_dof,
                "chi_square_p": _num(bias.chi_square_p),
                "mean_p_one": _num(bias.mean_p_one),
                "mean_z": _num(bias.mean_z),
                "mean_p": _num(bias.mean_p),
                "across_qubits_t": _num(bias.across_qubits_t),
                "across_qubits_p": _num(bias.across_qubits_p),
            },
            "qubits": qubits,
            "bitmap": {"size": BITMAP_SIZE, "rows": _rows(bitmap(q_stream, BITMAP_SIZE))},
            "next_bits": _next_bits(q_stream, q_attack, bias_attacker.split(shots) * n_qubits),
            "attacker": _attacker(q_attack),
        },
        "classical": {
            "n_bits": int(c_stream.size),
            "fraction_ones": _num(float(c_stream.mean())),
            "shannon_entropy": {"pooled": _num(shannon_entropy_per_bit(c_stream))},
            "bitmap": {"size": BITMAP_SIZE, "rows": _rows(bitmap(c_stream, BITMAP_SIZE))},
            "next_bits": _next_bits(c_stream, c_attack, c_attack.n_training_bits),
            "attacker": _attacker(c_attack),
        },
    }


def find_secret_like(text: str) -> list[str]:
    """Descriptions of every secret-like string or local path found in ``text``."""
    found = [f"pattern {p.pattern!r}" for p in _SECRET_PATTERNS if p.search(text)]
    for label, path in (("repo path", REPO_ROOT), ("home path", Path.home())):
        if str(path) in text:
            found.append(label)
    return found


def validate(demo: dict[str, Any]) -> None:
    """Raise ``ValueError`` if ``demo`` does not match ``demo.schema.json``."""
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(demo)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(part) for part in exc.absolute_path) or "(root)"
        raise ValueError(f"demo.json does not match its schema at {where}: {exc.message}") from None


def write_demo(folder: Path, out_path: Path | None = None, *, is_sample: bool) -> dict[str, Any]:
    """Build, check, and validate the export, then write it. Nothing is written on failure."""
    target = DEMO_JSON if out_path is None else out_path
    demo = build_demo(folder, is_sample=is_sample)
    text = json.dumps(demo, indent=1, allow_nan=False) + "\n"
    problems = find_secret_like(text)
    if problems:
        raise ValueError(f"refusing to write: secret-like content found ({', '.join(problems)})")
    validate(demo)
    size = len(text.encode("utf-8"))
    if size >= MAX_BYTES:
        raise ValueError(f"refusing to write: {size} bytes is over the {MAX_BYTES} byte limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return demo
