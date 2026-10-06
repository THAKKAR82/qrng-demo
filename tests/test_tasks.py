import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.paths import REPO_ROOT
from pipeline.tasks import TASKS, VersionRow, main, read_pins, ui_package_rows


def test_read_pins_follows_includes(tmp_path: Path) -> None:
    (tmp_path / "base.txt").write_text("# comment\nnumpy==2.0.0\n", encoding="utf-8")
    (tmp_path / "dev.txt").write_text(
        "-r base.txt\n-e .\nruff==0.1.0  # trailing\n", encoding="utf-8"
    )
    assert read_pins(tmp_path / "dev.txt") == {"numpy": "2.0.0", "ruff": "0.1.0"}


def test_repo_requirements_are_all_pinned() -> None:
    pins = read_pins(REPO_ROOT / "requirements-dev.txt")
    assert {"numpy", "qiskit", "qiskit-ibm-runtime", "pytest", "ruff"} <= pins.keys()


def test_version_row_status() -> None:
    assert VersionRow("a", "1", "1").status == "ok"
    assert VersionRow("a", "1", "2").status == "MISMATCH"
    assert VersionRow("a", "1", None).status == "MISSING"


def test_ui_package_rows(tmp_path: Path) -> None:
    manifest = {"dependencies": {"react": "19.0.0"}, "devDependencies": {"vite": "8.0.0"}}
    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    react_dir = tmp_path / "node_modules" / "react"
    react_dir.mkdir(parents=True)
    (react_dir / "package.json").write_text('{"version": "19.0.0"}', encoding="utf-8")
    rows = {row.name: row.status for row in ui_package_rows(tmp_path)}
    assert rows == {"react": "ok", "vite": "MISSING"}


def test_unknown_task_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["no-such-task"])
    assert excinfo.value.code == 2


def test_registered_tasks_and_human_only() -> None:
    assert set(TASKS) == {"setup-check", "make-sample", "collect-classical", "collect-quantum"}
    assert {name for name, task in TASKS.items() if task.human_only} == {"collect-quantum"}


def test_collect_quantum_cli_builds_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipeline import quantum

    seen: list[quantum.CollectConfig] = []

    def fake_run_task(cfg: quantum.CollectConfig) -> int:
        seen.append(cfg)
        return 0

    monkeypatch.setattr(quantum, "run_task", fake_run_task)
    assert main(["collect-quantum", "--shots", "100", "--qubits", "7", "--backend", "ibm_fez"]) == 0
    assert main(["collect-quantum", "--no-qubit-selection", "--dry-run"]) == 0
    assert main(["collect-quantum", "--physical-qubits", "3,7,12"]) == 0
    first, second, third = seen
    assert (first.shots, first.n_qubits, first.backend_name, first.select_qubits) == (
        100,
        7,
        "ibm_fez",
        True,
    )
    assert (second.shots, second.n_qubits) == (2000, 100)
    assert second.select_qubits is False
    assert second.dry_run is True
    assert third.physical_qubits == [3, 7, 12]
    assert third.n_qubits == 3


def test_collect_classical_cli_standalone_sample(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import pipeline.tasks as tasks

    monkeypatch.setattr(tasks, "SAMPLE_DIR", tmp_path)
    monkeypatch.setattr(tasks, "REPO_ROOT", tmp_path)
    assert main(["collect-classical", "--sample", "c", "--bits", "100"]) == 0
    assert (tmp_path / "c" / "classical.npz").is_file()
    assert main(["collect-classical", "--sample", "empty"]) == 1


def test_collect_classical_cli_missing_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pipeline.tasks as tasks

    monkeypatch.setattr(tasks, "RUNS_DIR", tmp_path)
    assert main(["collect-classical", "--run", "nope"]) == 1


def test_setup_check_touches_no_credentials(tmp_path: Path) -> None:
    """Run setup-check with HOME pointed at an empty dir and confirm it stays clean.

    It must not import qiskit_ibm_runtime and must not create or read ~/.qiskit.
    """
    script = (
        "import sys\n"
        "from pipeline.tasks import main\n"
        "main(['setup-check'])\n"
        "print('IMPORTED_RUNTIME=' + str('qiskit_ibm_runtime' in sys.modules))\n"
    )
    env = {**os.environ, "HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "IMPORTED_RUNTIME=False" in result.stdout
    assert "python" in result.stdout
    assert not (tmp_path / ".qiskit").exists()
