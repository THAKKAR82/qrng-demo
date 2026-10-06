"""Run-folder helpers shared by the collectors. See SPEC.md, Section 5.3."""

from __future__ import annotations

import json
import platform
import re
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

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
