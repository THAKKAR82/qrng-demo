import json
import os
import subprocess
import sys
from collections.abc import Callable
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
    assert set(TASKS) == {
        "setup-check",
        "make-sample",
        "collect-classical",
        "notebook",
        "collect-quantum",
        "export",
        "ui-dev",
        "ui-build",
        "live-server",
        "rebuild",
        "refresh",
        "check-site",
    }
    assert {name for name, task in TASKS.items() if task.human_only} == {
        "collect-quantum",
        "live-server",
        "refresh",
        "check-site",
    }


def test_human_only_tasks_are_denied_to_claude() -> None:
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    for name, task in TASKS.items():
        if task.human_only:
            assert f"Bash(*pipeline.tasks {name}*)" in deny
            assert f"Bash(*pipeline/tasks.py {name}*)" in deny


@pytest.mark.parametrize("flag", ["--host", "--bind"])
@pytest.mark.parametrize("address", ["0.0.0.0", "127.0.0.1", "192.168.1.20"])
def test_live_server_refuses_any_bind_option(
    flag: str, address: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pipeline import live

    def never(**_: object) -> int:
        raise AssertionError("live-server must refuse before starting")

    monkeypatch.setattr(live, "run_task", never)
    assert main(["live-server", flag, address]) == 2
    assert "127.0.0.1 only" in capsys.readouterr().out


def test_live_server_cli_passes_port_and_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipeline import live

    seen: list[dict[str, object]] = []

    def fake_run_task(**kwargs: object) -> int:
        seen.append(kwargs)
        return 0

    monkeypatch.setattr(live, "run_task", fake_run_task)
    assert main(["live-server"]) == 0
    assert main(["live-server", "--port", "9000", "--backend", "ibm_fez"]) == 0
    assert seen == [
        {"port": live.DEFAULT_PORT, "backend_name": None},
        {"port": 9000, "backend_name": "ibm_fez"},
    ]
    with pytest.raises(SystemExit):
        main(["live-server", "--port", "80"])


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
    assert main(["collect-quantum", "--from-job", "d3abc"]) == 0
    first, second, third, fourth = seen
    assert fourth.from_job == "d3abc"
    assert fourth.dry_run is False
    with pytest.raises(SystemExit):
        main(["collect-quantum", "--from-job", "d3abc", "--dry-run"])
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


class _NpmCalls:
    """Records ``npm run`` calls instead of running them."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[list[str], Path]] = []
        self.envs: list[dict[str, str] | None] = []
        self.on_call: Callable[[str, dict[str, str] | None], None] | None = None

    def __call__(
        self, args: list[str], *, cwd: Path, check: bool, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        self.calls.append((args, cwd))
        self.envs.append(env)
        if self.on_call is not None:
            self.on_call(args[-1], env)
        return subprocess.CompletedProcess(args, self.returncode)


@pytest.fixture
def fake_ui(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, _NpmCalls]:
    from pipeline import tasks

    ui_dir = tmp_path / "ui"
    (ui_dir / "node_modules").mkdir(parents=True)
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    npm = _NpmCalls()
    monkeypatch.setattr(tasks, "UI_DIR", ui_dir)
    monkeypatch.setattr(tasks, "DEMO_DIR", demo_dir)
    monkeypatch.setattr(tasks, "REPO_ROOT", tmp_path)
    monkeypatch.setattr("pipeline.tasks.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("pipeline.tasks.subprocess.run", npm)
    return ui_dir, demo_dir, npm


def test_ui_dev_runs_npm_dev_in_ui(fake_ui: tuple[Path, Path, _NpmCalls]) -> None:
    ui_dir, _, npm = fake_ui
    assert main(["ui-dev"]) == 0
    assert npm.calls == [(["/usr/bin/npm", "run", "dev"], ui_dir)]


def test_ui_build_runs_build_demo_and_checks_output(
    fake_ui: tuple[Path, Path, _NpmCalls], capsys: pytest.CaptureFixture[str]
) -> None:
    ui_dir, demo_dir, npm = fake_ui
    assert main(["ui-build"]) == 1  # the build "succeeded" but wrote nothing
    assert npm.calls == [(["/usr/bin/npm", "run", "build:demo"], ui_dir)]
    (demo_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    assert main(["ui-build"]) == 0
    assert "demo/index.html" in capsys.readouterr().out


def test_ui_build_passes_on_npm_failure(fake_ui: tuple[Path, Path, _NpmCalls]) -> None:
    _, _, npm = fake_ui
    npm.returncode = 2
    assert main(["ui-build"]) == 2


def test_ui_tasks_need_installed_dependencies(
    fake_ui: tuple[Path, Path, _NpmCalls], capsys: pytest.CaptureFixture[str]
) -> None:
    ui_dir, _, npm = fake_ui
    (ui_dir / "node_modules").rmdir()
    assert main(["ui-dev"]) == 1
    assert npm.calls == []
    assert "npm ci" in capsys.readouterr().out


def _step(steps: list[str], name: str, code: int = 0) -> Callable[[object], int]:
    """A stand-in task that records its name and returns ``code``."""

    def run(_: object) -> int:
        steps.append(name)
        return code

    return run


# --- setup-check ---------------------------------------------------------------------------


def test_python_version_problem() -> None:
    from pipeline.tasks import python_version_problem

    assert python_version_problem((3, 11, 0)) is None
    assert python_version_problem((3, 13, 9)) is None
    message = python_version_problem((3, 9, 6))
    assert message is not None
    assert "3.9.6" in message
    assert "python3.13 -m venv .venv" in message


def test_shadowed_tools(tmp_path: Path) -> None:
    from pipeline.tasks import VENV_TOOLS, shadowed_tools

    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    inside = {tool: str(venv_bin / tool) for tool in VENV_TOOLS}
    assert shadowed_tools(venv_bin, inside.get) == []
    # A venv built from Anaconda's Python is fine: only where the tools resolve matters.
    conda = {**inside, "pytest": "/opt/anaconda3/bin/pytest"}
    assert shadowed_tools(venv_bin, conda.get) == [("pytest", "/opt/anaconda3/bin/pytest")]
    missing = {k: v for k, v in inside.items() if k != "ruff"}
    assert shadowed_tools(venv_bin, missing.get) == [("ruff", None)]


@pytest.mark.skipif(not hasattr(os, "chflags"), reason="macOS file flags only")
def test_hidden_pth_files(tmp_path: Path) -> None:
    import stat

    from pipeline.tasks import hidden_pth_files

    site_packages = tmp_path / "lib" / "python3.13" / "site-packages"
    site_packages.mkdir(parents=True)
    visible = site_packages / "other.pth"
    visible.write_text("", encoding="utf-8")
    hidden = site_packages / "__editable__.qrng_demo-0.1.0.pth"
    hidden.write_text("", encoding="utf-8")
    assert hidden_pth_files(tmp_path) == []
    os.chflags(hidden, stat.UF_HIDDEN)
    assert hidden_pth_files(tmp_path) == [hidden]


def test_setup_check_prints_the_chflags_fix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pipeline import tasks

    pth = tmp_path / "__editable__.qrng_demo-0.1.0.pth"
    monkeypatch.setattr(tasks, "hidden_pth_files", lambda: [pth])
    assert main(["setup-check"]) == 1
    assert f'chflags nohidden "{pth}"' in capsys.readouterr().out


# --- rebuild and refresh -------------------------------------------------------------------


@pytest.fixture
def fake_rebuild(
    fake_ui: tuple[Path, Path, _NpmCalls], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, _NpmCalls, list[str]]:
    """rebuild with export, the notebook, and npm replaced by fakes that write outputs."""
    from pipeline import export as exporter
    from pipeline import site, tasks

    ui_dir, demo_dir, npm = fake_ui
    root = ui_dir.parent
    steps: list[str] = []
    demo_json = root / "demo.json"
    demo_json.write_text(json.dumps({"metadata": {"synthetic": False}}), encoding="utf-8")
    monkeypatch.setattr(exporter, "DEMO_JSON", demo_json)
    monkeypatch.setattr(tasks, "export", _step(steps, "export"))
    monkeypatch.setattr(tasks, "notebook", _step(steps, "notebook"))
    dist_index = ui_dir / "dist" / "index.html"
    demo_index = demo_dir / "index.html"
    web = ui_dir / "dist-web"
    monkeypatch.setattr(site, "QR_BUILDS", (dist_index, demo_index))
    monkeypatch.setattr(site, "WEB_DIST_DIR", web)
    site_json = root / "site.json"
    site_json.write_text(
        json.dumps(
            {
                "host": "cloudflare-pages",
                "project": "qrng-talk",
                "url": "https://qrng-talk.pages.dev/",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(site, "SITE_JSON", site_json)
    monkeypatch.setattr(site.load_site, "__defaults__", (site_json,))

    def build(script: str, env: dict[str, str] | None) -> None:
        steps.append(script)
        url = (env or {}).get("VITE_AUDIENCE_URL", "")
        meta = f'<meta name="qrng-audience-url" content="{url}" />'
        if script == "build":
            dist_index.parent.mkdir(parents=True, exist_ok=True)
            dist_index.write_text(meta, encoding="utf-8")
        elif script == "build:demo":
            demo_index.write_text(meta, encoding="utf-8")
        else:
            web.mkdir(parents=True, exist_ok=True)
            for name in ("index.html", "_headers", "404.html"):
                (web / name).write_text("x", encoding="utf-8")

    npm.on_call = build
    return site_json, npm, steps


def test_rebuild_builds_every_mode_with_the_site_url(
    fake_rebuild: tuple[Path, _NpmCalls, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, npm, steps = fake_rebuild
    assert main(["rebuild"]) == 0
    assert steps == ["export", "notebook", "build", "build:demo", "build:web"]
    assert all(
        env is not None and env["VITE_AUDIENCE_URL"] == "https://qrng-talk.pages.dev/"
        for env in npm.envs
    )
    assert "qrng-talk.pages.dev" in capsys.readouterr().out


def test_rebuild_with_the_placeholder_builds_without_a_qr_code(
    fake_rebuild: tuple[Path, _NpmCalls, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    site_json, npm, _ = fake_rebuild
    site_json.write_text(
        json.dumps(
            {
                "host": "cloudflare-pages",
                "project": "CHOOSE-A-NAME",
                "url": "https://CHOOSE-A-NAME.pages.dev/",
            }
        ),
        encoding="utf-8",
    )
    assert main(["rebuild"]) == 0
    assert all(env is not None and env["VITE_AUDIENCE_URL"] == "" for env in npm.envs)
    assert "NO QR code" in capsys.readouterr().out


def test_rebuild_rehearsal_override_and_bad_urls(
    fake_rebuild: tuple[Path, _NpmCalls, list[str]],
) -> None:
    _, npm, _ = fake_rebuild
    rehearsal = "http://192.168.1.20:4173/?view=audience"
    assert main(["rebuild", "--audience-url", rehearsal]) == 0
    assert npm.envs[-1] is not None and npm.envs[-1]["VITE_AUDIENCE_URL"] == rehearsal
    assert main(["rebuild", "--audience-url", 'https://x.pages.dev/"><b>']) == 1


def test_rebuild_fails_when_a_build_is_missing_its_qr_url(
    fake_rebuild: tuple[Path, _NpmCalls, list[str]],
) -> None:
    from pipeline import site

    _, npm, _ = fake_rebuild
    original = npm.on_call
    assert original is not None

    def stale_demo(script: str, env: dict[str, str] | None) -> None:
        original(script, None if script == "build:demo" else env)

    npm.on_call = stale_demo
    assert main(["rebuild"]) == 1
    assert site.built_audience_url(site.QR_BUILDS[1].read_text(encoding="utf-8")) == ""


def test_rebuild_fails_on_source_maps(fake_rebuild: tuple[Path, _NpmCalls, list[str]]) -> None:
    from pipeline import site

    _, npm, _ = fake_rebuild
    original = npm.on_call
    assert original is not None

    def with_map(script: str, env: dict[str, str] | None) -> None:
        original(script, env)
        if script == "build:web":
            (site.WEB_DIST_DIR / "index.js.map").write_text("{}", encoding="utf-8")

    npm.on_call = with_map
    assert main(["rebuild"]) == 1


def test_refresh_collects_then_rebuilds(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipeline import tasks

    steps: list[str] = []
    result = {"collect": 0}

    def collect(_: object) -> int:
        steps.append("collect")
        return result["collect"]

    monkeypatch.setattr(tasks, "collect_quantum", collect)
    monkeypatch.setattr(tasks, "rebuild", _step(steps, "rebuild"))
    assert main(["refresh"]) == 0
    assert steps == ["collect", "rebuild"]
    steps.clear()
    result["collect"] = 1
    assert main(["refresh"]) == 1
    assert steps == ["collect"]
    steps.clear()
    assert main(["refresh", "--dry-run"]) == 2
    assert steps == []


def test_check_site_refuses_the_placeholder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pipeline import site

    site_json = tmp_path / "site.json"
    site_json.write_text(
        json.dumps(
            {
                "host": "cloudflare-pages",
                "project": "CHOOSE-A-NAME",
                "url": "https://CHOOSE-A-NAME.pages.dev/",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(site.load_site, "__defaults__", (site_json,))
    monkeypatch.setattr(site, "http_fetch", lambda url: pytest.fail("check-site fetched"))
    assert main(["check-site"]) == 1
    assert "placeholder" in capsys.readouterr().out
