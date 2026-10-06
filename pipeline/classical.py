"""Classical stream: Python's ``random`` (MT19937), exactly as SPEC.md, Section 5.1 defines it.

The seed comes from ``os.urandom`` and is discarded as soon as the generator exists. It is
never stored, logged, or returned; only the generator's outputs leave this module.
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pipeline import runs

WORD_BITS = 32
GENERATOR = "random.Random (MT19937)"


def _fresh_generator() -> random.Random:
    # The seed exists only as this call's argument; nothing keeps a reference to it.
    return random.Random(int.from_bytes(os.urandom(32), "big"))


def words_needed(n_bits: int) -> int:
    """Whole 32-bit words needed to cover ``n_bits`` (rounded up)."""
    if n_bits <= 0:
        raise ValueError("n_bits must be positive")
    return -(-n_bits // WORD_BITS)


def generate_words(n_words: int) -> npt.NDArray[np.uint32]:
    """``n_words`` outputs of ``getrandbits(32)`` from a freshly seeded generator."""
    rng = _fresh_generator()
    return np.fromiter(
        (rng.getrandbits(WORD_BITS) for _ in range(n_words)), dtype=np.uint32, count=n_words
    )


def words_to_bits(words: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    """Unpack words most significant bit first: ``w`` gives ``(w >> 31) & 1, ..., w & 1``."""
    big_endian = np.asarray(words, dtype=np.uint32).astype(">u4")
    return np.unpackbits(big_endian.view(np.uint8))


def bits_to_words(bits: npt.ArrayLike) -> npt.NDArray[np.uint32]:
    """Pack bits into words most significant bit first (the inverse of ``words_to_bits``).
    Trailing bits that do not fill a whole word are dropped."""
    flat = np.asarray(bits, dtype=np.uint8).reshape(-1)
    whole = flat[: flat.size - flat.size % WORD_BITS]
    return np.packbits(whole).view(">u4").astype(np.uint32)


def quantum_bit_count(folder: Path) -> int:
    with np.load(folder / runs.QUANTUM_NPZ) as data:
        return int(data["bits"].size)


def write_classical(
    folder: Path,
    n_bits: int,
    *,
    run_id: str,
    synthetic: bool,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Generate words covering ``n_bits`` and write ``classical.npz`` + ``classical.json``."""
    npz_path = folder / runs.CLASSICAL_NPZ
    json_path = folder / runs.CLASSICAL_JSON
    if not overwrite and (npz_path.exists() or json_path.exists()):
        raise FileExistsError(f"{folder.name} already has classical data; run folders are final.")

    n_words = words_needed(n_bits)
    words = generate_words(n_words)
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz_path, words=words)

    meta: dict[str, Any] = {
        "schema_version": runs.SCHEMA_VERSION,
        "run_id": run_id,
        "created_utc": runs.iso_utc(runs.utc_now()),
        "synthetic": synthetic,
        "generator": GENERATOR,
        "seed_source": "os.urandom",
        "seed_bytes": 32,
        "seed_stored": False,
        "seed_discarded": True,
        "method": "getrandbits(32)",
        "n_words": n_words,
        "word_bits": WORD_BITS,
        "bit_order": "msb_first",
        "matched_bits": n_bits,
        "n_bits": n_words * WORD_BITS,
        "software": runs.software_versions(),
    }
    runs.write_json(json_path, meta)
    return meta


def collect_for_folder(
    folder: Path, *, n_bits: int | None = None, overwrite: bool = False
) -> dict[str, Any]:
    """Add classical data to ``folder``, matching its quantum bit count when it has one."""
    quantum_json = folder / runs.QUANTUM_JSON
    has_quantum = (folder / runs.QUANTUM_NPZ).is_file()
    if n_bits is None:
        if not has_quantum:
            raise FileNotFoundError(
                f"{folder.name} has no {runs.QUANTUM_NPZ}; pass a bit count instead."
            )
        n_bits = quantum_bit_count(folder)
    elif has_quantum and n_bits != quantum_bit_count(folder):
        raise ValueError("Bit count must match the quantum stream in the same folder.")

    synthetic = True
    if quantum_json.is_file():
        synthetic = bool(runs.read_json(quantum_json)["synthetic"])
    return write_classical(
        folder, n_bits, run_id=folder.name, synthetic=synthetic, overwrite=overwrite
    )
