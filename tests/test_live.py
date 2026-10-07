"""Live-server tests (SPEC.md, Section 6.4). Mocked service and Sampler only.

The server runs in-process on a random 127.0.0.1 port. conftest.py makes constructing a
real QiskitRuntimeService, or a Sampler on anything but local Aer, fail the test at once.
"""

from __future__ import annotations

import base64
import http.client
import itertools
import json
import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from qiskit_ibm_runtime.fake_provider import FakeFez
from requests.exceptions import ConnectionError as RequestsConnectionError

from pipeline import analysis, export, live, quantum, runs
from pipeline.live import LiveConfig, LiveController, LiveServer, LiveServerRefused
from pipeline.paths import LIVE_DIR, REPO_ROOT, RUNS_DIR, SAMPLE_DIR
from tests.test_quantum import FAKE_CRN, FAKE_TOKEN, FakeJob, FakeService, answers, no_input

# --- Fakes -------------------------------------------------------------------------------


class LiveSampler:
    """A Sampler factory and Sampler in one. Never touches the network."""

    def __init__(
        self,
        statuses: list[str] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.statuses = statuses
        self.fail = fail
        self.options: dict[str, Any] | None = None
        self.calls: list[tuple[Any, int]] = []

    def __call__(self, backend: Any, options: dict[str, Any]) -> LiveSampler:
        self.options = options
        return self

    def run(self, pubs: list[Any], *, shots: int) -> FakeJob:
        if self.fail is not None:
            raise self.fail
        (circuit,) = pubs
        self.calls.append((circuit, shots))
        rng = np.random.default_rng(len(self.calls))
        bits = (rng.random((shots, circuit.num_clbits)) < 0.45).astype(np.uint8)
        return FakeJob(bits, list(self.statuses or ["QUEUED", "RUNNING", "DONE"]))


def armed_config(sampler: LiveSampler, **service_kwargs: Any) -> LiveConfig:
    service = FakeService(**service_kwargs)
    return live.arm(
        backend_name=None,
        service_factory=lambda _: service,
        sampler_factory=sampler,
        input_fn=answers("fake_fez"),
    )


def wait_for(
    controller: LiveController, run_id: str, stages: set[str], timeout: float = 10.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = controller.status(run_id)
        assert status is not None
        if status["stage"] in stages:
            return status
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} never reached {stages}: {controller.status(run_id)}")


# --- Arming ------------------------------------------------------------------------------


def test_arming_reuses_collector_checks_and_live_settings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sampler = LiveSampler()
    service = FakeService()
    prompts = answers("fake_fez")
    config = live.arm(
        backend_name=None,
        service_factory=lambda _: service,
        sampler_factory=sampler,
        input_fn=prompts,
    )
    sub = config.submission
    assert sub.backend_name == "fake_fez"
    assert sub.shots == 200
    assert len(sub.physical_qubits) == 10
    assert sub.selection["method"] == "lowest_readout_error"
    errors = quantum.readout_errors(FakeFez())
    assert sub.physical_qubits == quantum.select_lowest_error(errors, 10)
    assert config.options["max_execution_time"] == 30
    assert config.options["default_shots"] == 200
    assert config.options["environment"]["job_tags"] == ["qrng-demo", "live"]
    assert config.options["twirling"]["enable_measure"] is False
    assert service.least_busy_kwargs == {"operational": True, "simulator": False}
    assert "fake_fez" in prompts.prompts[-1]
    out = capsys.readouterr().out
    assert "Open Plan: confirmed" in out
    assert "at most 3 live runs" in out
    assert "max_execution_time 30 s" in out
    assert "200 (2000 bits)" in out
    assert "crn" not in out.lower()


@pytest.mark.parametrize(
    ("service_kwargs", "reply", "reason"),
    [
        (
            {
                "instances": [
                    {"crn": FAKE_CRN, "plan": "premium", "pricing_type": "paid", "name": "x"}
                ]
            },
            None,
            "plan is 'premium'",
        ),
        ({"usage": {"usage_remaining_seconds": 30.0}}, None, "only 30 s"),
        ({"usage": {"usage_remaining_seconds": 80.0}}, None, "could use up to 90 s"),
        ({"usage": {}}, None, "did not report"),
        ({}, "ibm_torino", "Not confirmed"),
        ({}, "", "Not confirmed"),
    ],
)
def test_arming_refusals_leave_the_server_unarmed(
    service_kwargs: dict[str, Any],
    reply: str | None,
    reason: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakeService(**service_kwargs)
    config = live.try_arm(
        backend_name=None,
        service_factory=lambda _: service,
        sampler_factory=LiveSampler(),
        input_fn=answers(reply) if reply is not None else no_input,
    )
    assert config is None
    out = capsys.readouterr().out
    assert "Live mode NOT armed" in out
    assert reason in out
    assert "crn:v1" not in out
    health = LiveController(None).health()
    assert health["armed"] is False
    assert health["runs_remaining"] == 0


def test_arming_refuses_a_simulator() -> None:
    backend = FakeFez()
    backend.configuration().simulator = True
    service = FakeService(backend=backend)
    assert (
        live.try_arm(
            backend_name=None,
            service_factory=lambda _: service,
            sampler_factory=LiveSampler(),
            input_fn=no_input,
        )
        is None
    )


def test_arming_network_failure_is_short_and_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    def broken(_: str) -> Any:
        raise RequestsConnectionError(f"https://x/{FAKE_CRN}?token={FAKE_TOKEN}")

    assert live.try_arm(backend_name=None, service_factory=broken, input_fn=no_input) is None
    out = capsys.readouterr().out
    assert "network problem" in out
    assert "crn:v1" not in out
    assert FAKE_TOKEN not in out


def test_real_service_and_sampler_are_blocked_in_tests() -> None:
    # The conftest safety net: no mocking mistake can reach IBM.
    with pytest.raises(AssertionError, match="never construct"):
        live.arm(backend_name=None, input_fn=no_input)
    import qiskit_ibm_runtime
    from qiskit_ibm_runtime.executor_sampler import Sampler

    with pytest.raises(AssertionError, match="never construct"):
        qiskit_ibm_runtime.QiskitRuntimeService(name="qrng-open")
    with pytest.raises(AssertionError, match="never construct"):
        Sampler(mode=FakeFez())


def test_run_task_refuses_without_a_terminal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def never(_: str) -> Any:
        raise AssertionError("must refuse before loading the account")

    code = live.run_task(is_interactive=lambda: False, dist_dir=tmp_path, service_factory=never)
    assert code == 2
    assert "interactive terminal" in capsys.readouterr().out


def test_run_task_needs_a_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def never(_: str) -> Any:
        raise AssertionError("must refuse before loading the account")

    code = live.run_task(is_interactive=lambda: True, dist_dir=tmp_path, service_factory=never)
    assert code == 1
    assert "npm run build" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ('<meta name="qrng-audience-url" content="https://example.org/qrng/" />', "example.org"),
        ('<meta name="qrng-audience-url" content="" />', "NOT SET"),
        ('<meta name="qrng-audience-url" content="ftp://x" />', "not an http(s) URL"),
        ("", "unknown"),
    ],
)
def test_startup_reports_the_builds_audience_url(meta: str, expected: str) -> None:
    page = f"<html><head>{meta}</head><body></body></html>"
    assert expected in live.describe_audience_url(page)


def test_audience_url_is_unescaped() -> None:
    page = '<meta name="qrng-audience-url" content="https://e.org/?a=1&amp;b=2" />'
    assert live.built_audience_url(page) == "https://e.org/?a=1&b=2"


# --- Runs --------------------------------------------------------------------------------


def test_a_live_run_goes_through_each_stage_and_is_saved(tmp_path: Path) -> None:
    sampler = LiveSampler(["QUEUED", "QUEUED", "RUNNING", "DONE"])
    config = armed_config(sampler)
    seen: list[str] = []
    clock = itertools.count(0, 7)

    def record_stage(_: float) -> None:
        seen.extend(run.stage for run in controller.unfinished())

    controller = LiveController(
        config, live_dir=tmp_path, sleep=record_stage, clock=lambda: float(next(clock))
    )
    status, body = controller.start_run()
    assert status == 202
    run_id = body["id"]
    done = wait_for(controller, run_id, {"done", "failed"})
    assert done["stage"] == "done", done
    assert seen[0] == "queued"
    assert "running" in seen
    assert done["job_id"] == "d3fakejob0000000000"
    assert done["error"] is None

    result = done["result"]
    (folder,) = tmp_path.iterdir()
    meta = runs.read_json(folder / runs.QUANTUM_JSON)
    with np.load(folder / runs.QUANTUM_NPZ) as data:
        bits = data["bits"]
    assert meta["live"] is True
    assert meta["source"] == "ibm_quantum_hardware"
    assert meta["job"]["job_id"] == result["job_id"]
    assert not (folder / runs.CLASSICAL_NPZ).exists()
    assert bits.shape == (200, 10)
    assert export.is_live_run(folder)

    assert (result["shots"], result["n_qubits"], result["n_bits"]) == (200, 10, 2000)
    assert result["backend"] == "fake_fez"
    assert result["backend_num_qubits"] == 156
    assert result["physical_qubits"] == config.submission.physical_qubits
    assert result["qubit_selection"] == {
        "method": "lowest_readout_error",
        "candidates": len(quantum.readout_errors(FakeFez())),
    }
    assert export.unpack_bits(result["bits"], 2000).tolist() == bits.reshape(-1).tolist()
    assert result["p_one"] == pytest.approx(analysis.bias_per_qubit(bits).tolist())
    assert result["fraction_ones"] == pytest.approx(bits.mean())
    assert result["shannon_entropy"]["pooled"] == pytest.approx(
        analysis.shannon_entropy_per_bit(bits)
    )
    assert result["shannon_entropy"]["per_qubit_mean"] == pytest.approx(
        analysis.per_qubit_shannon_entropy(bits).mean()
    )
    assert result["qpu_seconds"] == 2.0
    assert result["submitted_utc"].endswith("Z")
    assert result["completed_utc"] == "2026-10-05T10:01:30Z"
    assert controller.health()["runs_remaining"] == 2


def test_queued_reports_elapsed_time(tmp_path: Path) -> None:
    release = threading.Event()
    now = [100.0]
    sampler = LiveSampler(["QUEUED", "DONE"])
    controller = LiveController(
        armed_config(sampler),
        live_dir=tmp_path,
        sleep=lambda _: release.wait(5),
        clock=lambda: now[0],
    )
    _, body = controller.start_run()
    status = wait_for(controller, body["id"], {"queued"})
    assert status["job_id"] == "d3fakejob0000000000"
    now[0] = 165.0
    assert controller.status(body["id"])["elapsed_seconds"] == 65  # type: ignore[index]
    assert [run.job_id for run in controller.unfinished()] == ["d3fakejob0000000000"]
    release.set()
    assert wait_for(controller, body["id"], {"done", "failed"})["stage"] == "done"


def test_one_run_at_a_time_and_the_cap_counts_every_start(tmp_path: Path) -> None:
    release = threading.Event()
    sampler = LiveSampler(["QUEUED", "QUEUED", "QUEUED", "DONE"])
    controller = LiveController(
        armed_config(sampler), live_dir=tmp_path, sleep=lambda _: release.wait(5)
    )
    status, first = controller.start_run()
    assert status == 202
    wait_for(controller, first["id"], {"queued"})
    status, body = controller.start_run()
    assert status == 409
    assert body == {"error": "A live run is still in progress."}
    release.set()
    wait_for(controller, first["id"], {"done", "failed"})

    sampler.fail = RuntimeError("submission failed")
    for _ in range(2):
        status, body = controller.start_run()
        assert status == 202
        assert wait_for(controller, body["id"], {"done", "failed"})["stage"] == "failed"
    assert controller.health()["runs_remaining"] == 0
    status, body = controller.start_run()
    assert status == 429
    assert "No live runs are left" in body["error"]
    assert len(sampler.calls) == 1  # failed submissions still counted


def test_unarmed_controller_refuses_to_start() -> None:
    status, body = LiveController(None).start_run()
    assert status == 503
    assert body == {"error": "Live mode is not available."}


@pytest.mark.parametrize("final", ["ERROR", "CANCELLED"])
def test_a_failed_job_is_reported_without_details(
    final: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    controller = LiveController(
        armed_config(LiveSampler(["QUEUED", final])), live_dir=tmp_path, sleep=lambda _: None
    )
    _, body = controller.start_run()
    status = wait_for(controller, body["id"], {"done", "failed"})
    assert status["stage"] == "failed"
    assert status["error"] == f"The job ended as {final}."
    assert status["job_id"] == "d3fakejob0000000000"
    assert status["result"] is None
    assert list(tmp_path.iterdir()) == []
    assert "crn:v1" not in capsys.readouterr().out


def test_submission_errors_never_reach_the_client(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = f"boom {FAKE_CRN} {FAKE_TOKEN} {Path.home()} qrng-open"
    controller = LiveController(
        armed_config(LiveSampler(fail=RuntimeError(secret))), live_dir=tmp_path
    )
    _, body = controller.start_run()
    status = wait_for(controller, body["id"], {"failed"})
    text = json.dumps(status)
    assert status["error"] == "The live run could not be completed (RuntimeError)."
    for leaked in ("crn:", FAKE_TOKEN, str(Path.home()), "qrng-open"):
        assert leaked not in text
    out = capsys.readouterr().out
    assert "crn:v1" not in out
    assert FAKE_TOKEN not in out


def test_save_live_run_needs_the_live_flag(tmp_path: Path) -> None:
    bits = np.zeros((2, 2), dtype=np.uint8)
    with pytest.raises(ValueError, match="marked live"):
        live.save_live_run(bits, {"run_id": "x"}, tmp_path)
    folder = live.save_live_run(bits, {"run_id": "x", "live": True}, tmp_path)
    with pytest.raises(quantum.CollectionAborted, match="never overwritten"):
        live.save_live_run(bits, {"run_id": "x", "live": True}, tmp_path)
    assert folder.parent == tmp_path


# --- data/live/ isolation ----------------------------------------------------------------


def test_live_folder_is_separate_and_gitignored() -> None:
    assert not LIVE_DIR.is_relative_to(RUNS_DIR)
    assert LIVE_DIR.name == "live"
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/live/" in gitignore


def _copy_sample_as(target: Path, *, live_flag: Any = None) -> Path:
    shutil.copytree(SAMPLE_DIR / "synthetic-v1", target)
    if live_flag is not None:
        meta = runs.read_json(target / runs.QUANTUM_JSON)
        meta["live"] = live_flag
        runs.write_json(target / runs.QUANTUM_JSON, meta)
    return target


@pytest.mark.parametrize("flag", [True, "yes", 1])
def test_export_refuses_live_runs_anywhere(tmp_path: Path, flag: Any) -> None:
    folder = _copy_sample_as(tmp_path / "runs" / "2099-01-01T000000Z_ibm_fez", live_flag=flag)
    with pytest.raises(ValueError, match="live runs are never exported"):
        export.write_demo(folder, tmp_path / "demo.json", is_sample=False)
    assert not (tmp_path / "demo.json").exists()


def test_export_refuses_anything_under_data_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_dir = tmp_path / "live"
    monkeypatch.setattr(export, "LIVE_DIR", live_dir)
    folder = _copy_sample_as(live_dir / "2099-01-01T000000Z_ibm_fez")
    with pytest.raises(ValueError, match="live runs are never exported"):
        export.build_demo(folder, is_sample=False)


def test_export_never_picks_live_runs(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    older = _copy_sample_as(runs_dir / "2026-01-01T000000Z_ibm_fez")
    _copy_sample_as(tmp_path / "live" / "2099-01-01T000000Z_ibm_fez", live_flag=True)
    folder, is_sample = export.resolve_source(runs_dir=runs_dir, sample_dir=tmp_path / "none")
    assert (folder, is_sample) == (older, False)
    # A live folder dropped into runs/ by mistake is incomplete (no classical files), so it
    # is never "the latest run" either.
    stray = runs_dir / "2099-01-01T000000Z_ibm_fez"
    stray.mkdir()
    shutil.copy(tmp_path / "live" / stray.name / runs.QUANTUM_JSON, stray)
    shutil.copy(tmp_path / "live" / stray.name / runs.QUANTUM_NPZ, stray)
    assert export.find_latest_run(runs_dir) == older


# --- HTTP and security -------------------------------------------------------------------


INDEX = (
    "<!doctype html><html><head><title>QRNG demo</title>"
    '<meta name="qrng-audience-url" content="" /></head><body></body></html>'
)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(INDEX, encoding="utf-8")
    (folder / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the build", encoding="utf-8")
    return folder


class Served:
    def __init__(self, server: LiveServer) -> None:
        self.server = server
        self.port = server.port
        self.token = server.token
        self.host = f"127.0.0.1:{server.port}"

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        token: bool = True,
        host: str | None = None,
        body: bytes | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        sent = {"Host": self.host if host is None else host}
        if token:
            sent[live.TOKEN_HEADER] = self.token
        sent.update(headers or {})
        for name, value in sent.items():
            if value != "":
                conn.putheader(name, value)
        if body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        response = conn.getresponse()
        data = response.read()
        result = (response.status, {k.lower(): v for k, v in response.getheaders()}, data)
        conn.close()
        return result

    def json(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any]:
        status, _, data = self.request(method, path, **kwargs)
        return status, json.loads(data)


def _serve(controller: LiveController, dist: Path) -> Iterator[Served]:
    server = LiveServer(controller, port=0, dist_dir=dist)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield Served(server)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def armed(dist: Path, tmp_path: Path) -> Iterator[Served]:
    controller = LiveController(
        armed_config(LiveSampler()), live_dir=tmp_path / "live", sleep=lambda _: None
    )
    yield from _serve(controller, dist)


@pytest.fixture
def unarmed(dist: Path) -> Iterator[Served]:
    yield from _serve(LiveController(None), dist)


def test_server_binds_to_loopback_only(dist: Path) -> None:
    for host in ("0.0.0.0", "", "::", "localhost", "192.168.1.20"):
        with pytest.raises(LiveServerRefused, match=r"127\.0\.0\.1 only"):
            LiveServer(LiveController(None), port=0, host=host, dist_dir=dist)
    server = LiveServer(LiveController(None), port=0, dist_dir=dist)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_server_needs_a_build(tmp_path: Path) -> None:
    with pytest.raises(LiveServerRefused, match="npm run build"):
        LiveServer(LiveController(None), port=0, dist_dir=tmp_path)


def test_page_carries_the_session_token(armed: Served) -> None:
    status, headers, data = armed.request("GET", "/", token=False)
    page = data.decode()
    assert status == 200
    assert f'<meta name="qrng-live-token" content="{armed.token}" />' in page
    assert page.index("qrng-live-token") < page.index("</head>")
    assert headers["content-type"].startswith("text/html")
    assert headers["cache-control"] == "no-store"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert len(armed.token) >= 32
    other = LiveServer(LiveController(None), port=0, dist_dir=armed.server.dist_dir)
    try:
        assert other.token != armed.token  # a new token every session
    finally:
        other.server_close()


def test_static_files_stay_inside_the_build(armed: Served) -> None:
    status, headers, data = armed.request("GET", "/assets/app.js", token=False)
    assert (status, data) == (200, b"console.log(1)")
    assert "javascript" in headers["content-type"]
    for path in (
        "/../secret.txt",
        "/%2e%2e/secret.txt",
        "/assets/../../secret.txt",
        "/assets/%2e%2e%2f%2e%2e%2fsecret.txt",
        "/missing.js",
        "/assets%5c..%5c..%5csecret.txt",
    ):
        status, _, data = armed.request("GET", path, token=False)
        assert status == 404, path
        assert b"outside the build" not in data


def test_health_reports_armed_state(armed: Served, unarmed: Served) -> None:
    assert armed.json("GET", live.API_HEALTH) == (
        200,
        {
            "armed": True,
            "backend": "fake_fez",
            "backend_num_qubits": 156,
            "runs_remaining": 3,
            "max_runs": 3,
            "shots": 200,
            "n_qubits": 10,
        },
    )
    status, body = unarmed.json("GET", live.API_HEALTH)
    assert status == 200
    assert body["armed"] is False
    assert body["backend"] is None and body["backend_num_qubits"] is None
    assert unarmed.json("POST", live.API_RUNS) == (503, {"error": "Live mode is not available."})


def test_start_and_follow_a_run_over_http(armed: Served) -> None:
    status, body = armed.json("POST", live.API_RUNS, body=b'{"shots": 100000, "backend": "x"}')
    assert status == 202
    run_path = f"{live.API_RUNS}/{body['id']}"
    deadline = time.monotonic() + 10
    while True:
        status, run = armed.json("GET", run_path)
        assert status == 200
        if run["stage"] in ("done", "failed") or time.monotonic() > deadline:
            break
        time.sleep(0.02)
    assert run["stage"] == "done"
    assert run["result"]["shots"] == 200  # the request body chose nothing
    assert run["result"]["backend"] == "fake_fez"
    assert armed.json("GET", f"{live.API_RUNS}/0123456789abcdef")[0] == 404
    assert armed.json("GET", f"{live.API_RUNS}/not-a-run-id")[0] == 404


def test_oversized_bodies_are_refused(armed: Served) -> None:
    status, _ = armed.json("POST", live.API_RUNS, body=b"x" * (live.MAX_BODY_BYTES + 1))
    assert status == 413
    assert armed.json("GET", live.API_HEALTH)[1]["runs_remaining"] == 3


API_CALLS = [
    ("GET", live.API_HEALTH),
    ("POST", live.API_RUNS),
    ("GET", f"{live.API_RUNS}/0123456789abcdef"),
]


@pytest.mark.parametrize(("method", "path"), API_CALLS)
@pytest.mark.parametrize("token", [None, "", "wrong", "x" * 43])
def test_api_needs_the_token(armed: Served, method: str, path: str, token: str | None) -> None:
    headers = {} if token is None else {live.TOKEN_HEADER: token}
    status, body = armed.json(method, path, token=False, headers=headers)
    assert (status, body) == (403, {"error": "Forbidden."})
    assert armed.json("GET", live.API_HEALTH)[1]["runs_remaining"] == 3


def test_token_in_another_header_or_query_is_not_enough(armed: Served) -> None:
    for headers, path in (
        ({"Authorization": f"Bearer {armed.token}"}, live.API_RUNS),
        ({"Cookie": f"token={armed.token}"}, live.API_RUNS),
        ({}, f"{live.API_RUNS}?token={armed.token}"),
    ):
        assert armed.json("POST", path, token=False, headers=headers)[0] == 403
    assert armed.json("GET", live.API_HEALTH)[1]["runs_remaining"] == 3


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:{port}",
        "127.0.0.1",
        "localhost",
        "127.0.0.1:1",
        "127.0.0.2:{port}",
        "0.0.0.0:{port}",
        "[::1]:{port}",
        "LOCALHOST:{port}",
        "127.0.0.1:{port}.evil.example",
        "",
    ],
)
@pytest.mark.parametrize(("method", "path"), [("GET", "/"), *API_CALLS])
def test_bad_host_is_rejected_everywhere(armed: Served, host: str, method: str, path: str) -> None:
    status, _, data = armed.request(method, path, host=host.format(port=armed.port))
    assert status == 403
    assert armed.token.encode() not in data
    assert json.loads(data) == {"error": "Forbidden."}
    assert armed.json("GET", live.API_HEALTH)[1]["runs_remaining"] == 3


def test_both_loopback_names_are_accepted(armed: Served) -> None:
    for host in (f"127.0.0.1:{armed.port}", f"localhost:{armed.port}"):
        assert armed.request("GET", live.API_HEALTH, host=host)[0] == 200
        origin = {"Origin": f"http://{host}"}
        assert armed.request("GET", live.API_HEALTH, host=host, headers=origin)[0] == 200


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        "http://evil.example:{port}",
        "https://127.0.0.1:{port}",
        "http://127.0.0.1:1",
        "http://localhost:{port}",  # a different origin from the Host used
        "http://127.0.0.1:{port}/",
        "file://",
    ],
)
@pytest.mark.parametrize(("method", "path"), [("GET", "/"), *API_CALLS])
def test_foreign_origin_is_rejected(armed: Served, origin: str, method: str, path: str) -> None:
    headers = {"Origin": origin.format(port=armed.port)}
    status, body = armed.json(method, path, headers=headers)
    assert (status, body) == (403, {"error": "Forbidden."})
    assert armed.json("GET", live.API_HEALTH)[1]["runs_remaining"] == 3


@pytest.mark.parametrize(
    ("method", "path", "allow"),
    [
        ("POST", live.API_HEALTH, "GET"),
        ("PUT", live.API_HEALTH, "GET"),
        ("HEAD", live.API_HEALTH, "GET"),
        ("GET", live.API_RUNS, "POST"),
        ("PUT", live.API_RUNS, "POST"),
        ("DELETE", live.API_RUNS, "POST"),
        ("PATCH", live.API_RUNS, "POST"),
        ("OPTIONS", live.API_RUNS, "POST"),
        ("POST", f"{live.API_RUNS}/0123456789abcdef", "GET"),
        ("DELETE", f"{live.API_RUNS}/0123456789abcdef", "GET"),
        ("POST", "/", "GET, HEAD"),
        ("PUT", "/index.html", "GET, HEAD"),
        ("OPTIONS", "/", "GET, HEAD"),
    ],
)
def test_wrong_methods_are_refused(armed: Served, method: str, path: str, allow: str) -> None:
    status, headers, _ = armed.request(method, path)
    assert status == 405
    assert headers["allow"] == allow
    assert armed.json("GET", live.API_HEALTH)[1]["runs_remaining"] == 3


def test_unknown_methods_are_refused(armed: Served) -> None:
    status, headers, _ = armed.request("TRACE", "/")
    assert status == 501
    assert not any(name.startswith("access-control-") for name in headers)


def test_no_cors_headers_on_any_response(armed: Served) -> None:
    preflight = {
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": live.TOKEN_HEADER,
    }
    responses = [
        armed.request("GET", "/"),
        armed.request("GET", "/assets/app.js"),
        armed.request("GET", live.API_HEALTH),
        armed.request("GET", live.API_HEALTH, token=False),
        armed.request("OPTIONS", live.API_RUNS, headers=preflight, token=False),
        armed.request("OPTIONS", live.API_RUNS, headers={"Origin": f"http://{armed.host}"}),
        armed.request("POST", live.API_RUNS, headers={"Origin": "https://evil.example"}),
        armed.request("GET", "/missing"),
        armed.request("GET", "/", host="evil.example"),
    ]
    for status, headers, _ in responses:
        assert status != 204
        assert not any(name.startswith("access-control-") for name in headers), headers
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("cache-control") == "no-store"


def test_responses_holding_secrets_are_blocked(
    armed: Served, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    controller = armed.server.controller
    for leak in (str(REPO_ROOT / "data"), FAKE_CRN, FAKE_TOKEN, "qrng-open", "~/.qiskit"):
        monkeypatch.setattr(controller, "health", lambda leak=leak: {"armed": True, "x": leak})
        status, body = armed.json("GET", live.API_HEALTH)
        assert (status, body) == (500, {"error": "Internal error."}), leak
    assert "Blocked a live-server response" in capsys.readouterr().out


def test_account_override_is_scanned_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(quantum.ACCOUNT_ENV, "talk-account")
    assert live.unsafe_content({"x": "talk-account"}, None) == ["account name"]
    assert live.unsafe_content({"x": "fake_fez"}, "talk-account") == []


def test_result_bits_must_be_plain_packed_bits() -> None:
    bits = base64.b64encode(bytes(250)).decode()
    good = {"result": {"bits": bits, "n_bits": 2000, "job_id": "d3fakejob0000000000"}}
    assert live.unsafe_content(good, None) == []
    for bad in (
        {"bits": bits, "n_bits": 2001 + 8},
        {"bits": "not base64!", "n_bits": 8},
        {"bits": FAKE_CRN, "n_bits": 8},
        {"bits": bits, "n_bits": "2000"},
    ):
        assert live.unsafe_content({"result": bad}, None) != []


def test_errors_over_http_hold_no_secrets(dist: Path, tmp_path: Path) -> None:
    secret = f"{FAKE_CRN} {FAKE_TOKEN} {Path.home()} qrng-open"
    controller = LiveController(
        armed_config(LiveSampler(fail=RuntimeError(secret))), live_dir=tmp_path / "live"
    )
    for served in _serve(controller, dist):
        _, body = served.json("POST", live.API_RUNS)
        wait_for(controller, body["id"], {"failed"})
        status, _, data = served.request("GET", f"{live.API_RUNS}/{body['id']}")
        text = data.decode()
        assert status == 200
        assert json.loads(text)["stage"] == "failed"
        for leaked in ("crn:", FAKE_TOKEN, str(Path.home()), "qrng-open", served.token):
            assert leaked not in text
        assert export.find_secret_like(text) == []


def test_live_module_loads_accounts_only_through_the_collector() -> None:
    source = (REPO_ROOT / "pipeline" / "live.py").read_text(encoding="utf-8")
    assert "RuntimeService(" not in source
    assert "qiskit_ibm_runtime" not in source
