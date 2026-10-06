"""Run-folder helpers shared by the collectors. See SPEC.md, Section 5.3."""

from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

SCHEMA_VERSION = 1
MAX_RUN_FOLDER_BYTES = 10 * 1024 * 1024

QUANTUM_NPZ = "quantum.npz"
QUANTUM_JSON = "quantum.json"
CLASSICAL_NPZ = "classical.npz"
CLASSICAL_JSON = "classical.json"

_BACKEND_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(moment: datetime) -> str:
    """ISO 8601 in UTC with a ``Z`` suffix, to the second."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_id(moment: datetime, backend_name: str) -> str:
    """``YYYY-MM-DDTHHMMSSZ_<backend>``, for example ``2026-10-06T141500Z_ibm_fez``."""
    if not _BACKEND_NAME_RE.match(backend_name):
        raise ValueError(f"Unexpected backend name: {backend_name!r}")
    return f"{moment.astimezone(UTC).strftime('%Y-%m-%dT%H%M%SZ')}_{backend_name}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def folder_size_bytes(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def warn_if_large(folder: Path, limit: int = MAX_RUN_FOLDER_BYTES) -> bool:
    """Print a warning and return True if ``folder`` is over ``limit`` bytes."""
    size = folder_size_bytes(folder)
    if size > limit:
        print(
            f"WARNING: {folder.name} is {size / 1_048_576:.1f} MB, over the "
            f"{limit / 1_048_576:.0f} MB limit for committed run folders."
        )
        return True
    return False


def software_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for package in ("numpy", "qiskit", "qiskit-ibm-runtime"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


@dataclass(frozen=True)
class RunData:
    """One run folder (or sample folder) loaded as stored. Nothing is altered."""

    folder: Path
    quantum_meta: dict[str, Any]
    classical_meta: dict[str, Any]
    bits: npt.NDArray[np.uint8]  # (shots, qubits), columns in logical-qubit order
    words: npt.NDArray[np.uint32]  # classical getrandbits(32) outputs, in order

    @property
    def synthetic(self) -> bool:
        """True unless both metadata files positively say the data is not synthetic."""
        return bool(self.quantum_meta.get("synthetic", True)) or bool(
            self.classical_meta.get("synthetic", True)
        )

    def _qubit_field(self, key: str) -> list[Any]:
        by_column = {int(q["column"]): q for q in self.quantum_meta.get("qubits", [])}
        return [by_column.get(j, {}).get(key) for j in range(self.bits.shape[1])]

    def physical_qubits(self) -> list[int | None]:
        """Physical qubit per column; ``None`` where unknown (or ``"synthetic"``)."""
        return [
            q if isinstance(q, int) and not isinstance(q, bool) else None
            for q in self._qubit_field("physical_qubit")
        ]

    def readout_errors(self) -> list[float | None]:
        """Readout error per column at selection time; ``None`` where unknown."""
        return [
            float(e) if isinstance(e, int | float) and not isinstance(e, bool) else None
            for e in self._qubit_field("readout_error")
        ]


def load_run(folder: Path) -> RunData:
    """Read the four data files of a run folder (SPEC.md, Section 5.3)."""
    with np.load(folder / QUANTUM_NPZ) as data:
        bits = np.asarray(data["bits"], dtype=np.uint8)
    with np.load(folder / CLASSICAL_NPZ) as data:
        words = np.asarray(data["words"], dtype=np.uint32)
    return RunData(
        folder=folder,
        quantum_meta=read_json(folder / QUANTUM_JSON),
        classical_meta=read_json(folder / CLASSICAL_JSON),
        bits=bits,
        words=words,
    )
