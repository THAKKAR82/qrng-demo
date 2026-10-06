"""Single entry point for project tasks: ``python -m pipeline.tasks <task>``.

Tasks registered here must follow SPEC.md. In particular, ``setup-check`` reports
versions only: it never imports qiskit_ibm_runtime, never constructs a
QiskitRuntimeService, and never touches ~/.qiskit or any credentials. Collector modules
are imported lazily, inside the task that needs them.

``collect-quantum`` (without ``--dry-run``) is for the human only: it submits a real job.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from pipeline.paths import REPO_ROOT, RUNS_DIR, SAMPLE_DIR, UI_DIR

MIN_PYTHON = (3, 11)
_PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)")


@dataclass(frozen=True)
class Task:
    name: str
    help: str
    run: Callable[[argparse.Namespace], int]
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    human_only: bool = False


@dataclass(frozen=True)
class VersionRow:
    name: str
    expected: str | None
    installed: str | None

    @property
    def status(self) -> str:
        if self.installed is None:
            return "MISSING"
        if self.expected is not None and self.installed != self.expected:
            return "MISMATCH"
        return "ok"


def read_pins(requirements: Path) -> dict[str, str]:
    """Return ``{name: version}`` for ``name==version`` lines, following ``-r`` includes."""
    pins: dict[str, str] = {}
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(("-r ", "--requirement ")):
            included = requirements.parent / line.split(maxsplit=1)[1]
            pins.update(read_pins(included))
            continue
        match = _PIN_RE.match(line)
        if match:
            pins[match.group(1)] = match.group(2)
    return pins


def python_package_rows(pins: dict[str, str]) -> list[VersionRow]:
    rows = []
    for name, expected in pins.items():
        try:
            installed: str | None = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        rows.append(VersionRow(name, expected, installed))
    return rows


def ui_package_rows(ui_dir: Path) -> list[VersionRow]:
    """Compare ui/package.json pins with what is installed in ui/node_modules."""
    manifest = json.loads((ui_dir / "package.json").read_text(encoding="utf-8"))
    declared: dict[str, str] = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }
    rows = []
    for name, expected in declared.items():
        installed_manifest = ui_dir / "node_modules" / name / "package.json"
        installed = None
        if installed_manifest.is_file():
            installed = json.loads(installed_manifest.read_text(encoding="utf-8"))["version"]
        rows.append(VersionRow(name, expected, installed))
    return rows


def tool_version(command: Sequence[str]) -> str | None:
    if shutil.which(command[0]) is None:
        return None
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.stdout.strip() or None


def _print_rows(title: str, rows: Sequence[VersionRow]) -> None:
    print(f"\n{title}")
    width = max((len(r.name) for r in rows), default=0)
    for row in rows:
        expected = row.expected or "-"
        installed = row.installed or "-"
        print(
            f"  {row.name:<{width}}  pinned {expected:<12} installed {installed:<12} {row.status}"
        )


def setup_check(_: argparse.Namespace) -> int:
    """Report Python, Node, and package versions. Touches no credentials."""
    problems = 0

    py_ok = sys.version_info >= MIN_PYTHON
    problems += not py_ok
    print("Environment")
    print(f"  python   {platform.python_version()}  {'ok' if py_ok else 'TOO OLD (need 3.11+)'}")
    print(f"  venv     {'yes' if sys.prefix != sys.base_prefix else 'NO (activate .venv)'}")
    print(f"  platform {platform.platform()}")

    for label, command in (("node", ["node", "--version"]), ("npm", ["npm", "--version"])):
        version = tool_version(command)
        problems += version is None
        print(f"  {label:<8} {version or 'MISSING'}")

    py_rows = python_package_rows(read_pins(REPO_ROOT / "requirements-dev.txt"))
    _print_rows("Python packages (requirements-dev.txt)", py_rows)
    problems += sum(row.status != "ok" for row in py_rows)

    ui_rows = ui_package_rows(UI_DIR)
    _print_rows("UI packages (ui/package.json)", ui_rows)
    problems += sum(row.status != "ok" for row in ui_rows)

    print(f"\n{'OK' if problems == 0 else f'{problems} problem(s) found'}")
    return 0 if problems == 0 else 1


def _positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _qubit_list(text: str) -> list[int]:
    try:
        return [int(part) for part in text.split(",") if part.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("expected comma-separated integers, e.g. 3,7,12") from None


def _configure_make_sample(parser: argparse.ArgumentParser) -> None:
    from pipeline import sample

    parser.add_argument("--name", default=sample.SAMPLE_NAME, help="folder under data/sample/")


def make_sample(args: argparse.Namespace) -> int:
    from pipeline import sample

    folder = sample.make_sample(args.name)
    print(f"Wrote SYNTHETIC sample to {folder.relative_to(REPO_ROOT)} (not from quantum hardware).")
    return 0


def _configure_collect_classical(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--run", help="run id under data/runs/ (matches its quantum bit count)")
    target.add_argument("--sample", help="name under data/sample/ (standalone generation)")
    parser.add_argument(
        "--bits", type=_positive_int, help="bit count; required if the folder has no quantum data"
    )


def collect_classical(args: argparse.Namespace) -> int:
    from pipeline import classical

    if args.run:
        folder = RUNS_DIR / args.run
        if not folder.is_dir():
            print(f"No such run: {args.run}")
            return 1
        overwrite = False
    else:
        folder = SAMPLE_DIR / args.sample
        folder.mkdir(parents=True, exist_ok=True)
        overwrite = True
    try:
        meta = classical.collect_for_folder(folder, n_bits=args.bits, overwrite=overwrite)
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(exc)
        return 1
    print(
        f"Wrote {meta['n_words']} words ({meta['n_bits']} bits) to "
        f"{folder.relative_to(REPO_ROOT)}. Seed discarded, never stored."
    )
    return 0


def _configure_collect_quantum(parser: argparse.ArgumentParser) -> None:
    from pipeline import quantum

    parser.add_argument("--shots", type=_positive_int, default=quantum.DEFAULT_SHOTS)
    parser.add_argument(
        "--qubits",
        type=_positive_int,
        default=quantum.DEFAULT_QUBITS,
        help="number of qubits N (capped at the backend size)",
    )
    parser.add_argument("--backend", help="backend name (default: least busy operational)")
    parser.add_argument(
        "--no-qubit-selection",
        action="store_true",
        help="use physical qubits 0..N-1 instead of the N lowest-readout-error qubits",
    )
    parser.add_argument(
        "--physical-qubits",
        type=_qubit_list,
        help="explicit physical qubits, e.g. 3,7,12 (overrides --qubits)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="plan on a local fake backend and run the real Sampler on Aer; no account, "
        "no network, writes nothing to data/runs/",
    )
    mode.add_argument(
        "--from-job",
        metavar="JOB_ID",
        help="HUMAN ONLY: write the run folder for an already-submitted job; submits nothing",
    )


def collect_quantum(args: argparse.Namespace) -> int:
    from pipeline import quantum

    cfg = quantum.CollectConfig(
        shots=args.shots,
        n_qubits=len(args.physical_qubits) if args.physical_qubits else args.qubits,
        backend_name=args.backend,
        select_qubits=not args.no_qubit_selection,
        physical_qubits=args.physical_qubits,
        dry_run=args.dry_run,
        from_job=args.from_job,
    )
    return quantum.run_task(cfg)


TASKS: dict[str, Task] = {
    task.name: task
    for task in (
        Task(
            "setup-check",
            "Report Python, Node, and package versions (no credentials).",
            setup_check,
        ),
        Task(
            "make-sample",
            "Regenerate the SYNTHETIC sample in data/sample/ (offline).",
            make_sample,
            _configure_make_sample,
        ),
        Task(
            "collect-classical",
            "Generate the classical MT19937 stream for a run or a sample (offline).",
            collect_classical,
            _configure_collect_classical,
        ),
        Task(
            "collect-quantum",
            "HUMAN ONLY: submit a real IBM Quantum job (--dry-run is safe, offline).",
            collect_quantum,
            _configure_collect_quantum,
            human_only=True,
        ),
    )
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.tasks", description=__doc__)
    sub = parser.add_subparsers(dest="task", metavar="<task>", required=True)
    for task in TASKS.values():
        task_parser = sub.add_parser(task.name, help=task.help, description=task.help)
        if task.configure is not None:
            task.configure(task_parser)
    args = parser.parse_args(argv)
    return TASKS[args.task].run(args)


if __name__ == "__main__":
    sys.exit(main())
