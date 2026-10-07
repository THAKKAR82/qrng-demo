"""Export one run (or the synthetic sample) to ``ui/src/data/demo.json`` for the UI.

The output follows ``ui/src/data/demo.schema.json`` (documented in ``SCHEMA.md``) and is
validated against it before anything is written. Fields are copied from the run's
metadata by an explicit allow-list, never wholesale, and the serialized output is checked
for secret-like strings and local paths. See SPEC.md, Section 7.1.
"""

from __future__ import annotations

import base64
import json
import math
import re
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import numpy.typing as npt

from pipeline import layout, runs, wording
from pipeline.analysis import (
    analyze_bias,
    bias_direction,
    bitmap,
    min_entropy_from_accuracy,
    per_qubit_shannon_entropy,
    shannon_entropy_per_bit,
    wilson_interval,
)
from pipeline.attacker import (
    AttackResult,
    BiasAttacker,
    MersenneTwisterAttacker,
    cross_checks,
)
from pipeline.classical import words_to_bits
from pipeline.paths import LIVE_DIR, REPO_ROOT, RUNS_DIR, SAMPLE_DIR, UI_DATA_DIR
from pipeline.sample import SAMPLE_NAME

DEMO_JSON = UI_DATA_DIR / "demo.json"
SCHEMA_JSON = UI_DATA_DIR / "demo.schema.json"
DEMO_SCHEMA_VERSION = 2
MAX_BYTES = 1_000_000
BITMAP_SIZE = 128
POOL_BITS = 20_000
SPOT_SIZE = 64  # spot images are SPOT_SIZE x SPOT_SIZE bits
SPOT_IMAGES = 10  # at most this many spot images per stream

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


def min_entropy_high(result: AttackResult) -> float:
    """The highest H∞ for any accuracy in the 95% interval: 1 bit if the interval contains
    0.5, otherwise H∞ at the bound nearer 0.5."""
    if result.consistent_with_chance:
        return 1.0
    return max(min_entropy_from_accuracy(result.ci_low), min_entropy_from_accuracy(result.ci_high))


def _running(result: AttackResult) -> dict[str, Any]:
    """Running accuracy with its 95% Wilson interval at every point."""
    index = result.running_index
    # running_accuracy is (hits so far) / index, so this recovers the exact hit counts.
    hits = np.rint(result.running_accuracy * index).astype(np.int64)
    bounds = [wilson_interval(int(h), int(n)) for h, n in zip(hits, index, strict=True)]
    return {
        "n_bits": [int(i) for i in index],
        "accuracy": [_num(float(a)) for a in result.running_accuracy],
        "ci_low": [_num(low) for low, _ in bounds],
        "ci_high": [_num(high) for _, high in bounds],
    }


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
        "min_entropy_high": _num(min_entropy_high(result)),
        "running": _running(result),
    }


def _cross_check(result: AttackResult) -> dict[str, Any]:
    return {
        "name": result.attacker,
        "accuracy": _num(result.accuracy),
        "ci_low": _num(result.ci_low),
        "ci_high": _num(result.ci_high),
        "n_predicted": result.n_predicted,
        "n_training_bits": result.n_training_bits,
        "min_entropy": _num(result.min_entropy),
        "consistent_with_half": result.consistent_with_chance,
        "running": _running(result),
    }


def pack_bits(bits: npt.ArrayLike) -> str:
    """Bits packed 8 per byte, most significant bit first, then base64 (SCHEMA.md, pool)."""
    packed = np.packbits(np.asarray(bits, dtype=np.uint8).reshape(-1), bitorder="big")
    return base64.b64encode(packed.tobytes()).decode("ascii")


def unpack_bits(text: str, n_bits: int) -> npt.NDArray[np.uint8]:
    """Inverse of ``pack_bits``."""
    packed = np.frombuffer(base64.b64decode(text), dtype=np.uint8)
    return np.unpackbits(packed, count=n_bits, bitorder="big")


def _pool(stream: npt.NDArray[np.uint8], result: AttackResult, start_bit: int) -> dict[str, Any]:
    """Held-out bits right after the attacker's training data, with its prediction for
    each, for the live displays and the guessing game. Refuses anything the attacker saw."""
    if start_bit < result.n_training_bits:
        raise ValueError(
            f"pool would start at bit {start_bit}, inside the {result.n_training_bits} "
            "training bits"
        )
    n = min(POOL_BITS, result.predictions.size, stream.size - start_bit)
    if n <= 0:
        raise ValueError("no held-out bits for the pool")
    return {
        "start_bit": start_bit,
        "n_bits": n,
        "bits": pack_bits(stream[start_bit : start_bit + n]),
        "predictions": pack_bits(result.predictions[:n]),
    }


def spot_segments(
    n_bits: int, avoid: tuple[int, int], *, size: int = SPOT_SIZE, count: int = SPOT_IMAGES
) -> list[int]:
    """Start bits of up to ``count`` non-overlapping segments of ``size * size`` bits, spread
    evenly through a stream of ``n_bits`` bits and never overlapping ``avoid`` (the pool's
    ``[start, end)``). The stream outside ``avoid`` is cut into whole tiles in order, and
    the chosen tiles are evenly spaced among them."""
    length = size * size
    low, high = avoid
    tiles: list[int] = []
    for span_start, span_end in ((0, low), (high, n_bits)):
        tiles.extend(range(span_start, span_end - length + 1, length))
    if len(tiles) <= count:
        return tiles
    picks = np.unique(np.rint(np.linspace(0, len(tiles) - 1, count)).astype(np.int64))
    return [tiles[int(i)] for i in picks]


def _spot(stream: npt.NDArray[np.uint8], pool: dict[str, Any]) -> dict[str, Any]:
    """Images for the phone game "Spot the quantum machine" (SPEC.md, Section 9.6)."""
    length = SPOT_SIZE * SPOT_SIZE
    avoid = (pool["start_bit"], pool["start_bit"] + pool["n_bits"])
    return {
        "size": SPOT_SIZE,
        "images": [
            {"start_bit": start, "bits": pack_bits(stream[start : start + length])}
            for start in spot_segments(int(stream.size), avoid)
        ],
    }


def _bitmap(stream: npt.NDArray[np.uint8], result: AttackResult) -> dict[str, Any]:
    return {
        "size": BITMAP_SIZE,
        "rows": _rows(bitmap(stream, BITMAP_SIZE)),
        "within_training": result.n_training_bits >= BITMAP_SIZE * BITMAP_SIZE,
    }


def _layout(backend_name: str | None, *, synthetic: bool) -> dict[str, Any] | None:
    found = None if synthetic else layout.device_layout(backend_name)
    if found is None:
        return None
    return {
        "description": layout.DESCRIPTION,
        "device": found.device,
        "qiskit_ibm_runtime_version": layout.runtime_version(),
        "num_qubits": found.num_qubits,
        "edges": [list(e) for e in found.edges],
        "coordinates": [list(c) for c in found.coordinates],
    }


def _summary(result: AttackResult) -> wording.AttackSummary:
    return wording.AttackSummary(
        n_correct=result.n_correct,
        n_predicted=result.n_predicted,
        accuracy=result.accuracy,
        ci_low=result.ci_low,
        ci_high=result.ci_high,
    )


def is_live_run(folder: Path) -> bool:
    """True if ``folder`` holds a live run from ``live-server`` (SPEC.md, Section 6.4).

    Fails safe: any ``live`` value other than a missing key or ``false`` counts as live.
    """
    meta_path = folder / runs.QUANTUM_JSON
    if not meta_path.is_file():
        return False
    return runs.read_json(meta_path).get("live", False) is not False


def build_demo(folder: Path, *, is_sample: bool) -> dict[str, Any]:
    if is_live_run(folder) or folder.resolve().is_relative_to(LIVE_DIR.resolve()):
        raise ValueError(
            f"refusing to export {folder.name}: live runs are never exported (SPEC.md, 6.4)"
        )
    run = runs.load_run(folder)
    q_meta, c_meta = run.quantum_meta, run.classical_meta
    q_bits, words = run.bits, run.words
    q_stream = q_bits.reshape(-1)
    c_stream = words_to_bits(words)
    shots, n_qubits = q_bits.shape

    synthetic = run.synthetic
    backend = q_meta.get("backend") or {}
    job = q_meta.get("job") or {}
    selection = q_meta.get("qubit_selection") or {}
    physical = run.physical_qubits()
    readout_errors = run.readout_errors()

    bias = analyze_bias(q_bits)
    bias_attacker = BiasAttacker()
    q_attack = bias_attacker.attack(q_bits)
    c_attack = MersenneTwisterAttacker().attack(words)
    assert q_attack.per_qubit_accuracy is not None
    cross = cross_checks(q_bits, words)

    per_qubit_entropy = per_qubit_shannon_entropy(q_bits)
    abs_bias = np.abs(bias.p_one - 0.5)
    worst = int(np.argmax(abs_bias))
    q_pool = _pool(q_stream, q_attack, bias_attacker.split(shots) * n_qubits)
    c_pool = _pool(c_stream, c_attack, c_attack.n_training_bits)
    c_entropy = shannon_entropy_per_bit(c_stream)
    q_entropy_mean = float(np.mean(per_qubit_entropy))
    copy = {
        "shannon_comparison": wording.shannon_comparison(c_entropy, q_entropy_mean),
        "classical_attack": wording.attack_phrase("classical", _summary(c_attack)),
        "quantum_attack": wording.attack_phrase("quantum", _summary(q_attack)),
        "unpredictability_comparison": wording.unpredictability_comparison(
            (c_attack.min_entropy_conservative, min_entropy_high(c_attack)),
            (q_attack.min_entropy_conservative, min_entropy_high(q_attack)),
        ),
        "bias_note": wording.bias_note(
            bias_direction(bias.p_one).direction, float(abs_bias.mean())
        ),
    }

    qubits = []
    for j in range(n_qubits):
        readout = readout_errors[j]
        qubits.append(
            {
                "column": j,
                "physical_qubit": physical[j],
                "readout_error": None if readout is None else _num(readout),
                "p_one": _num(float(bias.p_one[j])),
                "z": _num(float(bias.z_scores[j])),
                "flagged": j in bias.flagged,
                "shannon_entropy": _num(float(per_qubit_entropy[j])),
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
                "per_qubit_mean": _num(q_entropy_mean),
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
            "bitmap": _bitmap(q_stream, q_attack),
            "pool": q_pool,
            "spot": _spot(q_stream, q_pool),
            "attacker": _attacker(q_attack),
        },
        "classical": {
            "n_bits": int(c_stream.size),
            "fraction_ones": _num(float(c_stream.mean())),
            "shannon_entropy": {"pooled": _num(c_entropy)},
            "bitmap": _bitmap(c_stream, c_attack),
            "pool": c_pool,
            "spot": _spot(c_stream, c_pool),
            "attacker": _attacker(c_attack),
        },
        "cross_checks": {
            "mt_on_quantum": _cross_check(cross.mt_on_quantum),
            "bias_on_classical": _cross_check(cross.bias_on_classical),
        },
        "layout": _layout(backend.get("name"), synthetic=synthetic),
        "copy": copy,
    }


def find_secret_like(text: str) -> list[str]:
    """Descriptions of every secret-like string or local path found in ``text``."""
    found = [f"pattern {p.pattern!r}" for p in _SECRET_PATTERNS if p.search(text)]
    for label, path in (("repo path", REPO_ROOT), ("home path", Path.home())):
        if str(path) in text:
            found.append(label)
    return found


_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def _check_packed(text: Any, n_bits: int, where: str) -> str:
    if not isinstance(text, str) or not _BASE64_RE.match(text):
        raise ValueError(f"{where} is not plain base64")
    if len(base64.b64decode(text, validate=True)) != -(-n_bits // 8):
        raise ValueError(f"{where} does not hold {n_bits} bits")
    return "<packed bits>"


def scannable_text(demo: dict[str, Any]) -> str:
    """The serialized export with every packed-bits field (the pools and the spot images)
    replaced by a placeholder, for the secret scan: base64 bits look token-like by chance.
    Each replaced field must first be plain base64 that decodes to exactly the expected
    number of bits, so nothing else can hide there.
    """
    shallow = dict(demo)
    for stream in ("quantum", "classical"):
        part = shallow.get(stream)
        if not isinstance(part, dict):
            continue
        part = dict(part)
        if "pool" in part:
            pool = dict(part["pool"])
            for field in ("bits", "predictions"):
                pool[field] = _check_packed(pool[field], pool["n_bits"], f"{stream}.pool.{field}")
            part["pool"] = pool
        if "spot" in part:
            spot = dict(part["spot"])
            n = spot["size"] * spot["size"]
            spot["images"] = [
                {
                    **image,
                    "bits": _check_packed(image["bits"], n, f"{stream}.spot.images[{i}].bits"),
                }
                for i, image in enumerate(spot["images"])
            ]
            part["spot"] = spot
        shallow[stream] = part
    return json.dumps(shallow, indent=1, allow_nan=False)


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
    problems = find_secret_like(scannable_text(demo))
    if problems:
        raise ValueError(f"refusing to write: secret-like content found ({', '.join(problems)})")
    validate(demo)
    size = len(text.encode("utf-8"))
    if size >= MAX_BYTES:
        raise ValueError(f"refusing to write: {size} bytes is over the {MAX_BYTES} byte limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return demo
