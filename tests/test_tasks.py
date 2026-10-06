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


def test_only_safe_tasks_registered() -> None:
    # Collection tasks do not exist yet; when they are added they must be human-only.
    assert set(TASKS) == {"setup-check"}


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
