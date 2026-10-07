"""Single entry point for project tasks: ``python -m pipeline.tasks <task>``.

Tasks registered here must follow SPEC.md. In particular, ``setup-check`` reports
versions only: it never imports qiskit_ibm_runtime, never constructs a
QiskitRuntimeService, and never touches ~/.qiskit or any credentials. Collector modules
are imported lazily, inside the task that needs them.

``collect-quantum`` (without ``--dry-run``) is for the human only: it submits a real job.
``live-server`` is for the human only too: once armed, it can submit real jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from pipeline.paths import DEMO_DIR, REPO_ROOT, RUNS_DIR, SAMPLE_DIR, UI_DIR

MIN_PYTHON = (3, 11)
VENV_DIR = REPO_ROOT / ".venv"
# Tools the checks run by name; each must come from .venv, not another environment.
VENV_TOOLS = ("pytest", "mypy", "ruff")
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


def python_version_problem(version: tuple[int, ...] = tuple(sys.version_info[:3])) -> str | None:
    """Why this Python is too old for the project, or None if it is new enough."""
    if tuple(version[:2]) >= MIN_PYTHON:
        return None
    found = ".".join(str(v) for v in version[:3])
    return (
        f"Python {found} is too old: this project needs 3.11 or newer. On macOS, bare "
        "python3 is often Apple's 3.9. Recreate the venv with an explicit interpreter: "
        "rm -rf .venv && python3.13 -m venv .venv"
    )


def shadowed_tools(
    venv_bin: Path = VENV_DIR / "bin", which: Callable[[str], str | None] = shutil.which
) -> list[tuple[str, str | None]]:
    """Tools in VENV_TOOLS that don't resolve inside .venv/bin, with where they resolve."""
    inside = venv_bin.resolve()
    found = []
    for tool in VENV_TOOLS:
        location = which(tool)
        if location is None or Path(location).parent.resolve() != inside:
            found.append((tool, location))
    return found


def hidden_pth_files(venv: Path = VENV_DIR) -> list[Path]:
    """.pth files in the venv with macOS's hidden flag, which Python 3.13+ skips."""
    hidden = getattr(stat, "UF_HIDDEN", 0)
    if not hidden:
        return []
    return [
        pth
        for pth in sorted(venv.glob("lib/python*/site-packages/*.pth"))
        if getattr(pth.stat(), "st_flags", 0) & hidden
    ]


def setup_check(_: argparse.Namespace) -> int:
    """Report Python, Node, and package versions. Touches no credentials."""
    problems = 0
    warnings = 0

    too_old = python_version_problem()
    problems += too_old is not None
    print("Environment")
    print(f"  python   {platform.python_version()}  {'ok' if too_old is None else 'TOO OLD'}")
    if too_old is not None:
        print(f"           {too_old}")
    in_venv = Path(sys.prefix).resolve() == VENV_DIR.resolve()
    other = sys.prefix != sys.base_prefix and not in_venv
    venv_state = "yes (.venv)" if in_venv else "ANOTHER venv" if other else "NO"
    print(f"  venv     {venv_state}{'' if in_venv else ' (run: source .venv/bin/activate)'}")
    print(f"  platform {platform.platform()}")

    shadowed = shadowed_tools()
    for tool, location in shadowed:
        warnings += 1
        where = "is not on PATH" if location is None else f"resolves to {location}, outside .venv"
        print(f"  WARN     {tool} {where}")
    if shadowed:
        print("           Another environment (such as conda base) is ahead of .venv on PATH.")
        print("           Fix: conda deactivate, then source .venv/bin/activate")
        print("           (conda config --set auto_activate_base false keeps base off),")
        print("           or run each tool through the venv: python -m pytest, python -m mypy.")

    for pth in hidden_pth_files():
        problems += 1
        shown = pth.relative_to(REPO_ROOT) if pth.is_relative_to(REPO_ROOT) else pth
        print(f"  HIDDEN   {shown} has macOS's hidden flag; Python skips it,")
        print("           so the editable install of pipeline is invisible. Fix:")
        print(f'           chflags nohidden "{pth}"')

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

    status = "OK" if problems == 0 else f"{problems} problem(s) found"
    if warnings:
        status += f" ({warnings} warning(s) above)"
    print(f"\n{status}")
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


LIVE_DEFAULT_PORT = 8765  # pipeline.live.DEFAULT_PORT; not imported so parsing stays light


def _port(text: str) -> int:
    value = int(text)
    if not 1024 <= value <= 65535:
        raise argparse.ArgumentTypeError("must be between 1024 and 65535")
    return value


def _configure_live_server(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=_port, default=LIVE_DEFAULT_PORT)
    parser.add_argument("--backend", help="backend name (default: least busy operational)")
    # Accepted only to refuse them clearly: the server binds to 127.0.0.1 and nothing else.
    parser.add_argument("--host", help=argparse.SUPPRESS)
    parser.add_argument("--bind", help=argparse.SUPPRESS)


def live_server(args: argparse.Namespace) -> int:
    if args.host is not None or args.bind is not None:
        print(
            "Refusing: live-server binds to 127.0.0.1 only and cannot listen on any other address."
        )
        return 2
    from pipeline import live

    return live.run_task(port=args.port, backend_name=args.backend)


def _configure_export(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--run", help="run folder under data/runs/ (default: the latest)")
    source.add_argument("--sample", help="folder under data/sample/ (used when no run exists)")


def export(args: argparse.Namespace) -> int:
    from pipeline import export as exporter

    try:
        folder, is_sample = exporter.resolve_source(run=args.run, sample=args.sample)
        demo = exporter.write_demo(folder, is_sample=is_sample)
    except ValueError as exc:
        print(exc)
        return 1
    label = "SYNTHETIC sample" if demo["metadata"]["synthetic"] else "real run"
    target = exporter.DEMO_JSON
    shown = target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target
    print(f"Exported {label} {folder.name} to {shown}.")
    return 0


def _configure_notebook(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--run", help="run folder under data/runs/ (default: the latest)")
    source.add_argument("--sample", help="folder under data/sample/ (used when no run exists)")


def notebook(args: argparse.Namespace) -> int:
    from nbclient.exceptions import CellExecutionError

    from pipeline import notebook as runner

    try:
        target = runner.execute(run=args.run, sample=args.sample)
    except CellExecutionError as exc:
        print(f"The notebook failed:\n{exc}")
        return 1
    shown = target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target
    print(f"Executed the notebook into {shown}.")
    return 0


def _run_npm(script: str, env: dict[str, str] | None = None) -> int:
    """Run ``npm run <script>`` in ui/. The UI's own commands live in ui/package.json.

    ``env`` adds to (or overrides) this process's environment for the build.
    """
    npm = shutil.which("npm")
    if npm is None:
        print("npm was not found. Install Node (see .nvmrc) and try again.")
        return 1
    if not (UI_DIR / "node_modules").is_dir():
        print("UI dependencies are not installed. Run: (cd ui && npm ci)")
        return 1
    full_env = None if env is None else {**os.environ, **env}
    sys.stdout.flush()  # keep our lines in order with npm's when output is piped
    return subprocess.run([npm, "run", script], cwd=UI_DIR, check=False, env=full_env).returncode


def ui_dev(_: argparse.Namespace) -> int:
    """Start the Vite dev server; Ctrl-C stops it."""
    try:
        return _run_npm("dev")
    except KeyboardInterrupt:
        return 0


def ui_build(_: argparse.Namespace) -> int:
    """Build the single-file fallback demo/index.html from the current demo.json."""
    code = _run_npm("build:demo")
    if code != 0:
        return code
    target = DEMO_DIR / "index.html"
    if not target.is_file():
        print(f"The build finished but {target.relative_to(REPO_ROOT)} is missing.")
        return 1
    size_kib = target.stat().st_size / 1024
    shown = target.relative_to(REPO_ROOT)
    print(f"Wrote {shown} ({size_kib:.0f} KiB). It opens offline by double-click.")
    return 0


def _configure_rebuild(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--audience-url",
        help="build with this phone address instead of site.json's (for a rehearsal)",
    )


def _audience_url_for_build(override: str | None) -> str | None:
    """The VITE_AUDIENCE_URL to build with: --audience-url, else site.json's URL, else none."""
    from pipeline import site

    if override is not None:
        print(f"Audience URL (from --audience-url, for a rehearsal): {override}")
        return override
    config = site.load_site()
    if config.placeholder:
        print("!" * 72)
        print("site.json still holds the placeholder project name, so these builds have")
        print("NO audience URL and NO QR code. Choose the project name (DEPLOY.md, step 2),")
        print("set it in site.json, and run rebuild again before the talk.")
        print("!" * 72)
        return None
    print(f"Audience URL (from site.json): {config.url}  shown as {site.short_url(config.url)}")
    return config.url


def rebuild(args: argparse.Namespace) -> int:
    """Export demo.json, re-run the notebook, and build every UI mode. No QPU time."""
    from pipeline import export as exporter
    from pipeline import site

    try:
        url = _audience_url_for_build(args.audience_url)
    except site.SiteError as exc:
        print(f"site.json: {exc}")
        return 1
    if url is not None and not site.valid_audience_url(url):
        print(f"Refusing audience URL {url!r}: it must be http(s) with no quotes or markup.")
        return 1

    print("\n== export: demo.json from the latest committed run")
    code = export(argparse.Namespace(run=None, sample=None))
    if code != 0:
        return code
    demo = json.loads(exporter.DEMO_JSON.read_text(encoding="utf-8"))
    if demo["metadata"]["synthetic"]:
        print("WARNING: there is no committed run, so the builds use SYNTHETIC sample data.")

    print("\n== notebook")
    code = notebook(argparse.Namespace(run=None, sample=None))
    if code != 0:
        return code

    env = {"VITE_AUDIENCE_URL": url or ""}
    for script in ("build", "build:demo", "build:web"):
        print(f"\n== npm run {script}")
        code = _run_npm(script, env)
        if code != 0:
            return code

    print("\n== checking the builds")
    problems = 0
    for build in site.QR_BUILDS:
        shown = build.relative_to(REPO_ROOT)
        recorded = (
            site.built_audience_url(build.read_text(encoding="utf-8")) if build.is_file() else None
        )
        if recorded != (url or ""):
            problems += 1
            print(f"  FAIL {shown}: QR code points to {recorded!r}, expected {url or ''!r}")
        else:
            print(f"  ok   {shown}: QR code points to {url or 'nothing (no URL set)'}")
    web = site.WEB_DIST_DIR
    for name in ("index.html", "_headers", "404.html"):
        if not (web / name).is_file():
            problems += 1
            print(f"  FAIL ui/dist-web/{name} is missing")
    maps = sorted(p.relative_to(REPO_ROOT) for p in web.rglob("*.map"))
    if maps:
        problems += 1
        print(f"  FAIL the phone site holds source maps: {', '.join(map(str, maps))}")
    else:
        print("  ok   ui/dist-web/ holds index.html, _headers, 404.html, and no source maps")
    if problems:
        return 1
    print("\nRebuilt. Commit ui/src/data/demo.json and demo/index.html; deploy ui/dist-web/")
    print("(DEPLOY.md), then run: python -m pipeline.tasks check-site")
    print("To present: (cd ui && npm run serve), or live-server. Not npm run preview, which")
    print("rebuilds ui/dist/ without the audience URL.")
    return 0


def _configure_refresh(parser: argparse.ArgumentParser) -> None:
    _configure_collect_quantum(parser)
    _configure_rebuild(parser)


def refresh(args: argparse.Namespace) -> int:
    """HUMAN ONLY: collect-quantum (with all its confirmations), then rebuild."""
    if args.dry_run:
        print(
            "refresh never does a dry run. Use: python -m pipeline.tasks collect-quantum --dry-run"
        )
        return 2
    code = collect_quantum(args)
    if code != 0:
        print("collect-quantum did not finish, so nothing was rebuilt.")
        return code
    return rebuild(args)


def check_site(_: argparse.Namespace) -> int:
    """Fetch the deployed phone site named in site.json and check it (SPEC.md, 9.7)."""
    from pipeline import site

    try:
        config = site.load_site()
    except site.SiteError as exc:
        print(f"site.json: {exc}")
        return 1
    if config.placeholder:
        print("site.json still holds the placeholder project name; see DEPLOY.md, step 2.")
        return 1
    print(f"Checking {config.url} (contacts only this site)")
    report = site.check_site(config)
    failed = report.failures
    print(f"\n{'All checks passed.' if failed == 0 else f'{failed} check(s) failed.'}")
    return 0 if failed == 0 else 1


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
        Task(
            "live-server",
            "HUMAN ONLY: serve ui/dist/ with the live-run API on 127.0.0.1 (can submit real jobs).",
            live_server,
            _configure_live_server,
            human_only=True,
        ),
        Task(
            "export",
            "Write ui/src/data/demo.json from the latest run (or the sample) (offline).",
            export,
            _configure_export,
        ),
        Task(
            "notebook",
            "Execute notebooks/qrng_demo.ipynb into data/scratch/ (offline).",
            notebook,
            _configure_notebook,
        ),
        Task("ui-dev", "Start the UI dev server (npm run dev).", ui_dev),
        Task(
            "ui-build",
            "Build the single-file demo/index.html from ui/src/data/demo.json (offline).",
            ui_build,
        ),
        Task(
            "rebuild",
            "Export, re-run the notebook, and build every UI mode with site.json's URL (no QPU).",
            rebuild,
            _configure_rebuild,
        ),
        Task(
            "refresh",
            "HUMAN ONLY: collect-quantum (real job, with its confirmations), then rebuild.",
            refresh,
            _configure_refresh,
            human_only=True,
        ),
        Task(
            "check-site",
            "HUMAN ONLY: check the deployed phone site at site.json's URL (contacts only it).",
            check_site,
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
