"""Live mode: ``live-server`` (SPEC.md, Section 6.4). Run by the human only.

Serves the presenter build in ``ui/dist/`` and a small JSON API on 127.0.0.1, so the
Machines slide can run one small job on real hardware during the talk. Arming reuses the
collector's safeguards from ``pipeline.quantum``: an interactive terminal, the Open Plan
check, the allowance check, and typing the backend name. Without arming, the server only
serves the app and the API says live mode is unavailable.

Nothing runs at import time; the account is loaded only inside ``arm``. Tests run the
server in-process on a random port with a mocked service (tests/test_live.py).
"""

from __future__ import annotations

import hmac
import html
import json
import mimetypes
import re
import secrets
import shutil
import socketserver
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import numpy as np
import numpy.typing as npt

from pipeline import quantum, runs
from pipeline.paths import LIVE_DIR, REPO_ROOT, UI_DIST_DIR
from pipeline.quantum import CollectionAborted

BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LIVE_QUBITS = 10
LIVE_SHOTS = 200
MAX_LIVE_RUNS = 3
LIVE_MAX_EXECUTION_SECONDS = 30
LIVE_JOB_TAGS = ("qrng-demo", "live")
POLL_SECONDS = 2.0

TOKEN_HEADER = "X-QRNG-Live-Token"
TOKEN_META = "qrng-live-token"
AUDIENCE_META = "qrng-audience-url"
MAX_BODY_BYTES = 1024

API_PREFIX = "/api/"
API_HEALTH = "/api/live/health"
API_RUNS = "/api/live/runs"
_RUN_PATH_RE = re.compile(r"^/api/live/runs/([0-9a-f]{16})$")
_AUDIENCE_RE = re.compile(rf'<meta\s+name="{AUDIENCE_META}"\s+content="([^"]*)"\s*/?>')

FINAL_STAGES = frozenset({"done", "failed"})
_STAGE_FOR_STATUS = {"QUEUED": "queued", "RUNNING": "running"}

InputFn = Callable[[str], str]
SamplerFactory = Callable[[Any, dict[str, Any]], Any]


class LiveServerRefused(Exception):
    """The server will not start, with a short reason for the terminal."""


# --- Arming ------------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveConfig:
    """What an armed server runs. Fixed at arming; nothing the client sends changes it."""

    backend: Any
    submission: quantum.Submission
    plan: dict[str, Any]
    options: dict[str, Any]
    account: str
    sampler_factory: SamplerFactory
    max_runs: int = MAX_LIVE_RUNS


def live_options() -> dict[str, Any]:
    """The collector's explicit Sampler options, with the live limit and tags."""
    return quantum._validated_options(
        LIVE_SHOTS, max_execution_time=LIVE_MAX_EXECUTION_SECONDS, job_tags=LIVE_JOB_TAGS
    )


def print_live_config(sub: quantum.Submission, remaining_seconds: float) -> None:
    quantum.print_summary(sub, remaining_seconds)
    errors = ", ".join(
        f"{q}: {'?' if e is None else f'{e:.4f}'}"
        for q, e in zip(sub.physical_qubits, sub.readout_errors, strict=True)
    )
    print(f"Readout:   {errors}")
    print(
        f"Live mode: at most {MAX_LIVE_RUNS} live runs this session, "
        f"max_execution_time {LIVE_MAX_EXECUTION_SECONDS} s each"
    )
    print()


def arm(
    *,
    backend_name: str | None,
    account: str | None = None,
    service_factory: Callable[[str], Any] | None = None,
    sampler_factory: SamplerFactory | None = None,
    input_fn: InputFn = input,
) -> LiveConfig:
    """Run the collector's checks and ask the human to arm. Raises if not armed."""
    # Resolved at call time so tests can patch the collector's factories.
    service_factory = service_factory or quantum.load_service
    sampler_factory = sampler_factory or quantum.make_sampler
    account = account or quantum.account_name()

    options = live_options()
    print(f"Loading saved account {account!r} ...")
    service = service_factory(account)
    plan = quantum.check_open_plan(service, input_fn)
    remaining = quantum.check_allowance(service)
    needed = MAX_LIVE_RUNS * LIVE_MAX_EXECUTION_SECONDS
    if remaining < needed:
        raise CollectionAborted(
            f"Refusing: {remaining:.0f} s of QPU allowance left, but {MAX_LIVE_RUNS} live runs "
            f"could use up to {needed} s."
        )
    backend = quantum.pick_backend(service, backend_name)
    sub = quantum.plan_submission(
        backend,
        quantum.CollectConfig(
            shots=LIVE_SHOTS, n_qubits=LIVE_QUBITS, backend_name=backend_name, account=account
        ),
    )
    print_live_config(sub, remaining)
    answer = input_fn(
        f"Type the backend name ({sub.backend_name}) to arm live mode, "
        "anything else serves the app unarmed: "
    )
    if answer.strip() != sub.backend_name:
        raise CollectionAborted("Not confirmed.")
    return LiveConfig(
        backend=backend,
        submission=sub,
        plan=plan,
        options=options,
        account=account,
        sampler_factory=sampler_factory,
    )


def try_arm(**kwargs: Any) -> LiveConfig | None:
    """``arm``, but any refusal or failure leaves the server unarmed with a short reason."""
    account = kwargs.get("account") or quantum.account_name()
    try:
        config = arm(**kwargs)
    except CollectionAborted as exc:
        print(f"Live mode NOT armed: {quantum.redact(str(exc))}")
        return None
    except Exception as exc:
        print(f"Live mode NOT armed: {quantum.friendly_error(exc, account)}")
        return None
    print(f"Live mode ARMED on {config.submission.backend_name}.")
    return config


# --- Live runs ---------------------------------------------------------------------------


@dataclass
class LiveRun:
    run_id: str
    stage: str = "submitting"
    job_id: str | None = None
    submitted_at: float | None = None  # monotonic clock
    error: str | None = None
    result: dict[str, Any] | None = None


def save_live_run(bits: npt.NDArray[np.uint8], meta: dict[str, Any], live_dir: Path) -> Path:
    """Write ``quantum.npz`` and ``quantum.json`` (with ``"live": true``) to a new folder."""
    if meta.get("live") is not True:
        raise ValueError("live runs must be marked live")
    run_dir = live_dir / str(meta["run_id"])
    if run_dir.exists():
        raise CollectionAborted(
            f"{run_dir.name} already exists; live folders are never overwritten."
        )
    run_dir.mkdir(parents=True)
    try:
        np.savez_compressed(run_dir / runs.QUANTUM_NPZ, bits=bits)
        runs.write_json(run_dir / runs.QUANTUM_JSON, meta)
    except BaseException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run_dir


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def live_summary(bits: npt.NDArray[np.uint8], meta: dict[str, Any]) -> dict[str, Any]:
    """What the app gets for a finished live run, computed by ``pipeline.analysis``."""
    from pipeline import analysis, export

    per_qubit = analysis.per_qubit_shannon_entropy(bits)
    job = meta["job"]
    return {
        "backend": str(meta["backend"]["name"]),
        "job_id": str(job["job_id"]),
        "shots": int(bits.shape[0]),
        "n_qubits": int(bits.shape[1]),
        "n_bits": int(bits.size),
        "physical_qubits": [int(q["physical_qubit"]) for q in meta["qubits"]],
        "qubit_selection": {
            "method": str(meta["qubit_selection"]["method"]),
            "candidates": meta["qubit_selection"]["candidates"],
        },
        "bits": export.pack_bits(bits.reshape(-1)),
        "p_one": [float(p) for p in analysis.bias_per_qubit(bits)],
        "fraction_ones": float(bits.mean()),
        "shannon_entropy": {
            "pooled": analysis.shannon_entropy_per_bit(bits),
            "per_qubit_mean": float(per_qubit.mean()),
        },
        "submitted_utc": job["submitted_utc"],
        "completed_utc": job["completed_utc"],
        "qpu_seconds": _number_or_none(job["qpu_seconds"]),
    }


class LiveController:
    """The live runs of one server session. Thread-safe; the cap is enforced here."""

    def __init__(
        self,
        config: LiveConfig | None,
        *,
        live_dir: Path = LIVE_DIR,
        poll_seconds: float = POLL_SECONDS,
        sleep: Callable[[float], object] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._live_dir = live_dir
        self._poll_seconds = poll_seconds
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._runs: dict[str, LiveRun] = {}
        self._started = 0
        self.threads: list[threading.Thread] = []

    @property
    def account(self) -> str | None:
        return None if self._config is None else self._config.account

    def health(self) -> dict[str, Any]:
        config = self._config
        with self._lock:
            started = self._started
        if config is None:
            return {
                "armed": False,
                "backend": None,
                "runs_remaining": 0,
                "max_runs": 0,
                "shots": None,
                "n_qubits": None,
            }
        return {
            "armed": True,
            "backend": config.submission.backend_name,
            "runs_remaining": max(0, config.max_runs - started),
            "max_runs": config.max_runs,
            "shots": config.submission.shots,
            "n_qubits": len(config.submission.physical_qubits),
        }

    def start_run(self) -> tuple[HTTPStatus, dict[str, Any]]:
        """Accept a run and submit it in the background, or refuse with a reason."""
        config = self._config
        if config is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Live mode is not available."}
        with self._lock:
            if self._started >= config.max_runs:
                return HTTPStatus.TOO_MANY_REQUESTS, {
                    "error": "No live runs are left in this session."
                }
            if any(run.stage not in FINAL_STAGES for run in self._runs.values()):
                return HTTPStatus.CONFLICT, {"error": "A live run is still in progress."}
            # Counted on acceptance, whatever happens to the run afterwards.
            self._started += 1
            run = LiveRun(run_id=secrets.token_hex(8))
            self._runs[run.run_id] = run
        thread = threading.Thread(
            target=self._execute, args=(config, run), name=f"live-run-{run.run_id}", daemon=True
        )
        self.threads.append(thread)
        thread.start()
        return HTTPStatus.ACCEPTED, {"id": run.run_id, "stage": run.stage}

    def status(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            elapsed = (
                None if run.submitted_at is None else max(0, int(self._clock() - run.submitted_at))
            )
            return {
                "id": run.run_id,
                "stage": run.stage,
                "job_id": run.job_id,
                "elapsed_seconds": elapsed,
                "error": run.error,
                "result": run.result,
            }

    def unfinished(self) -> list[LiveRun]:
        with self._lock:
            return [run for run in self._runs.values() if run.stage not in FINAL_STAGES]

    def _update(self, run: LiveRun, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(run, key, value)

    def _wait(self, run: LiveRun, job: Any) -> str:
        while True:
            # Finality first, as in the collector, so a stale status can't be final.
            final = job.in_final_state()
            status = quantum._status_name(job.status())
            stage = _STAGE_FOR_STATUS.get(status)
            if stage is not None:
                self._update(run, stage=stage)
            if final:
                return status
            self._sleep(self._poll_seconds)

    def _execute(self, config: LiveConfig, run: LiveRun) -> None:
        sub = config.submission
        try:
            sampler = config.sampler_factory(config.backend, config.options)
            submitted = runs.utc_now()
            job = sampler.run([sub.isa_circuit], shots=sub.shots)
            job_id = quantum._check_job_id(str(job.job_id()))
            self._update(run, stage="submitted", job_id=job_id, submitted_at=self._clock())
            print(f"Live run submitted to {sub.backend_name}. Job ID: {job_id}")
            record = quantum.submission_record(
                sub=sub,
                plan=config.plan,
                job_id=job_id,
                submitted=submitted,
                options=config.options,
            )
            record["live"] = True

            status = self._wait(run, job)
            if status != "DONE":
                print(f"Live job {job_id} ended as {status}. Nothing was saved.")
                self._update(run, stage="failed", error=f"The job ended as {status}.")
                return
            bits = quantum.result_bits(job, record)
            meta = quantum.completed_record(job, record, bits)
            run_dir = save_live_run(bits, meta, self._live_dir)
            summary = live_summary(bits, meta)
        except Exception as exc:
            print(f"Live run failed: {quantum.friendly_error(exc, config.account)}")
            self._update(
                run,
                stage="failed",
                error=f"The live run could not be completed ({type(exc).__name__}).",
            )
            return
        self._update(run, stage="done", result=summary)
        print(f"Live job {job_id} done. Saved to {_shown(run_dir)}")


def _shown(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else path.name


# --- Response safety ---------------------------------------------------------------------


_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def scannable(body: dict[str, Any]) -> str:
    """The JSON body with the packed bits of a result replaced by a placeholder, after
    checking they are plain base64 of exactly the stated bit count (as the export does)."""
    import base64

    result = body.get("result")
    if isinstance(result, dict) and "bits" in result:
        packed = result["bits"]
        n_bits = result.get("n_bits")
        if (
            not isinstance(packed, str)
            or not isinstance(n_bits, int)
            or not _BASE64_RE.match(packed)
            or len(base64.b64decode(packed, validate=True)) != -(-n_bits // 8)
        ):
            raise ValueError("result.bits is not plain base64 of n_bits bits")
        body = {**body, "result": {**result, "bits": "<packed bits>"}}
    return json.dumps(body, allow_nan=False)


def unsafe_content(body: dict[str, Any], account: str | None) -> list[str]:
    """Why ``body`` must not be sent: secret-like strings, local paths, the account name."""
    from pipeline import export

    try:
        text = scannable(body)
    except ValueError as exc:
        return [str(exc)]
    problems = export.find_secret_like(text)
    for name in {quantum.account_name(), account}:
        if name and name in text:
            problems.append("account name")
    return problems


# --- HTTP --------------------------------------------------------------------------------


def inject_token(index_html: str, token: str) -> str:
    """The presenter page with the session token in a meta tag the app reads."""
    if "</head>" not in index_html:
        raise LiveServerRefused("ui/dist/index.html has no </head>; rebuild with: npm run build")
    if TOKEN_META in index_html:
        raise LiveServerRefused("ui/dist/index.html already holds a live token; rebuild it.")
    meta = f'<meta name="{TOKEN_META}" content="{html.escape(token)}" />'
    return index_html.replace("</head>", f"  {meta}\n  </head>", 1)


def built_audience_url(index_html: str) -> str | None:
    """The build's ``VITE_AUDIENCE_URL`` ("" when unset), or None if the build predates it."""
    match = _AUDIENCE_RE.search(index_html)
    return None if match is None else html.unescape(match.group(1))


def describe_audience_url(index_html: str) -> str:
    value = built_audience_url(index_html)
    if value is None:
        return (
            "Audience URL: unknown (this build predates the check). Rebuild with "
            "VITE_AUDIENCE_URL=<phone site> npm run build."
        )
    if value.strip() == "":
        return (
            "Audience URL: NOT SET in this build, so no QR code will show. For the talk, rebuild "
            "with VITE_AUDIENCE_URL=<hosted phone site> npm run build."
        )
    if not value.strip().startswith(("https://", "http://")):
        return f"Audience URL: {value!r} is not an http(s) URL, so no QR code will show."
    return f"Audience URL in this build (QR code): {value.strip()}"


_SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "frame-ancestors 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
)


class LiveServer(ThreadingHTTPServer):
    """The presenter app and the live API, on 127.0.0.1 only."""

    daemon_threads = True

    def __init__(
        self,
        controller: LiveController,
        *,
        port: int = DEFAULT_PORT,
        host: str = BIND_HOST,
        dist_dir: Path = UI_DIST_DIR,
        token: str | None = None,
    ) -> None:
        if host != BIND_HOST:
            raise LiveServerRefused(f"live-server binds to {BIND_HOST} only; refusing {host!r}.")
        self.controller = controller
        self.token = token or secrets.token_urlsafe(32)
        self.dist_dir = dist_dir.resolve()
        index = self.dist_dir / "index.html"
        if not index.is_file():
            raise LiveServerRefused(
                "ui/dist/index.html is missing. Build the presenter app first: npm run build"
            )
        self.index_html = inject_token(index.read_text(encoding="utf-8"), self.token).encode()
        super().__init__((BIND_HOST, port), LiveRequestHandler)
        bound_host, bound_port = self.server_address[:2]
        if bound_host != BIND_HOST:
            self.server_close()
            raise LiveServerRefused(f"Bound to {bound_host!r} instead of {BIND_HOST}.")
        self.port = int(bound_port)
        self.allowed_hosts = frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    def server_bind(self) -> None:
        # HTTPServer.server_bind looks up the host's FQDN, which can stall for seconds on
        # macOS; the name is never used here.
        socketserver.TCPServer.server_bind(self)
        self.server_name = BIND_HOST
        self.server_port = int(self.server_address[1])


class LiveRequestHandler(BaseHTTPRequestHandler):
    server: LiveServer
    server_version = "qrng-live-server"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet: the terminal shows the live runs' stages instead of every request."""

    def do_GET(self) -> None:
        self._handle("GET")

    def do_HEAD(self) -> None:
        self._handle("HEAD")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_PATCH(self) -> None:
        self._handle("PATCH")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def do_OPTIONS(self) -> None:
        self._handle("OPTIONS")

    # Every request passes the Host and Origin checks before anything else happens.
    def _handle(self, method: str) -> None:
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or hosts[0] not in self.server.allowed_hosts:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden."}, method)
            return
        origins = self.headers.get_all("Origin") or []
        if len(origins) > 1 or (origins and origins[0] != f"http://{hosts[0]}"):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden."}, method)
            return
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith(API_PREFIX):
            self._api(method, path)
        elif method in ("GET", "HEAD"):
            self._static(method, path)
        else:
            self._send_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "Method not allowed."},
                method,
                allow="GET, HEAD",
            )

    def _token_ok(self) -> bool:
        values = self.headers.get_all(TOKEN_HEADER) or []
        if len(values) != 1:
            return False
        return hmac.compare_digest(
            values[0].encode("utf-8", "replace"), self.server.token.encode("utf-8")
        )

    def _api(self, method: str, path: str) -> None:
        match = _RUN_PATH_RE.match(path)
        if path == API_HEALTH:
            allowed = "GET"
        elif path == API_RUNS:
            allowed = "POST"
        elif match is not None:
            allowed = "GET"
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."}, method)
            return
        if method != allowed:
            self._send_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "Method not allowed."},
                method,
                allow=allowed,
            )
            return
        if not self._token_ok():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Forbidden."}, method)
            return

        controller = self.server.controller
        if path == API_HEALTH:
            self._send_json(HTTPStatus.OK, controller.health(), method)
        elif path == API_RUNS:
            if not self._discard_body():
                return
            status, body = controller.start_run()
            self._send_json(status, body, method)
        else:
            assert match is not None
            found = controller.status(match.group(1))
            if found is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."}, method)
            else:
                self._send_json(HTTPStatus.OK, found, method)

    def _discard_body(self) -> bool:
        """Read and ignore the request body: the client chooses nothing about a run."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Bad request."}, "POST")
            return False
        if length:
            self.rfile.read(length)
        return True

    def _static(self, method: str, path: str) -> None:
        relative = unquote(path)
        if relative in ("/", "/index.html"):
            self._send(HTTPStatus.OK, self.server.index_html, "text/html; charset=utf-8", method)
            return
        dist = self.server.dist_dir
        if "\x00" in relative or "\\" in relative:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."}, method)
            return
        candidate = (dist / relative.lstrip("/")).resolve()
        if not candidate.is_relative_to(dist) or not candidate.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."}, method)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, candidate.read_bytes(), content_type, method)

    def _send_json(
        self, status: HTTPStatus, body: dict[str, Any], method: str, *, allow: str | None = None
    ) -> None:
        problems = unsafe_content(body, self.server.controller.account)
        if problems:
            print("Blocked a live-server response that looked like it held a secret or path.")
            status, body = HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal error."}
        payload = json.dumps(body, allow_nan=False).encode("utf-8")
        self._send(status, payload, "application/json; charset=utf-8", method, allow=allow)

    def _send(
        self,
        status: HTTPStatus,
        payload: bytes,
        content_type: str,
        method: str,
        *,
        allow: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if allow is not None:
            self.send_header("Allow", allow)
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(payload)


# --- Task --------------------------------------------------------------------------------


def run_task(
    *,
    port: int = DEFAULT_PORT,
    backend_name: str | None = None,
    is_interactive: Callable[[], bool] = lambda: sys.stdin.isatty(),
    dist_dir: Path = UI_DIST_DIR,
    **arm_kwargs: Any,
) -> int:
    """Entry point for ``python -m pipeline.tasks live-server``. Human only."""
    if not is_interactive():
        print("Refusing: live-server must be run from an interactive terminal.")
        return 2
    index = dist_dir / "index.html"
    if not index.is_file():
        print(
            "ui/dist/index.html is missing. Build the presenter app first: (cd ui && npm run build)"
        )
        return 1
    print(describe_audience_url(index.read_text(encoding="utf-8")))

    try:
        config = try_arm(backend_name=backend_name, **arm_kwargs)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    controller = LiveController(config)
    try:
        server = LiveServer(controller, port=port, dist_dir=dist_dir)
    except LiveServerRefused as exc:
        print(exc)
        return 2
    except OSError as exc:
        print(f"Could not listen on {BIND_HOST}:{port} ({exc.strerror or type(exc).__name__}).")
        return 1

    state = "ARMED" if config is not None else "unarmed (live control hidden)"
    print(f"\nServing the presenter app at http://{BIND_HOST}:{server.port}/  [{state}]")
    print("Open it in the browser on this laptop. Ctrl-C stops the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
        for run in controller.unfinished():
            what = f"Live job {run.job_id}" if run.job_id else "A live submission"
            print(f"{what} had not finished. It may still finish on IBM; it was not saved here.")
    return 0
