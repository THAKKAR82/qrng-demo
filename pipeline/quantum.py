"""Real IBM Quantum collection (SPEC.md, Sections 5.2 and 6.3). Run by the human only.

Nothing here runs at import time, and ``qiskit_ibm_runtime`` is imported only inside the
functions that need it. The account is loaded by saved-account *name*; this module never
handles tokens or CRNs, and it redacts anything CRN- or token-like from error messages.

Tests drive every step with a mocked service, backend, and Sampler.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pipeline import classical, runs
from pipeline.paths import RUNS_DIR

ACCOUNT_ENV = "QRNG_IBM_ACCOUNT"
DEFAULT_ACCOUNT = "qrng-open"
DEFAULT_QUBITS = 100
DEFAULT_SHOTS = 2_000
OPTIMIZATION_LEVEL = 1
MIN_REMAINING_SECONDS = 60.0
MAX_EXECUTION_SECONDS = 300
POLL_SECONDS = 5.0
DRY_RUN_BACKEND = "FakeFez"

REQUIRED_PLAN = "open"
REQUIRED_PRICING_TYPE = "free"
OPEN_PLAN_PHRASE = "open plan"

# Rough per-job overhead used only for the pre-submission estimate shown to the human.
_ESTIMATE_OVERHEAD_SECONDS = 2.0
_FALLBACK_REP_DELAY = 250e-6

_CRN_RE = re.compile(r"crn:[^\s'\"),;]*", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{32,}")

InputFn = Callable[[str], str]


class CollectionAborted(Exception):
    """A deliberate stop with a short, human-readable reason."""


def redact(text: str) -> str:
    """Remove anything that looks like a CRN or a long token from ``text``."""
    return _TOKEN_RE.sub("<redacted>", _CRN_RE.sub("crn:<redacted>", text))


def account_name() -> str:
    return os.environ.get(ACCOUNT_ENV) or DEFAULT_ACCOUNT


# --- Account and plan --------------------------------------------------------------------


def load_service(name: str) -> Any:
    """Load the saved account by name. Never pass or read tokens or CRNs here."""
    from qiskit_ibm_runtime import QiskitRuntimeService

    return QiskitRuntimeService(name=name)


def _plan_undetermined(reason: str, input_fn: InputFn, reported: dict[str, Any]) -> dict[str, Any]:
    print(f"Open Plan: could not be determined from the API ({reason}).")
    answer = input_fn(
        f"If you are sure this account is on the free Open Plan, type '{OPEN_PLAN_PHRASE}' "
        "to continue (anything else aborts): "
    )
    if answer.strip() != OPEN_PLAN_PHRASE:
        raise CollectionAborted("Open Plan not confirmed. Nothing was submitted.")
    print("Open Plan: confirmed by you (not by the API).")
    return {**reported, "verified_by": "human_typed_open_plan"}


def check_open_plan(service: Any, input_fn: InputFn) -> dict[str, Any]:
    """Require ``plan == "open"`` and ``pricing_type == "free"`` for the active instance.

    Values reported by the API that differ in any way are refused outright. If the values
    cannot be determined, the human must type ``open plan`` to continue. The CRN and instance
    name are never printed or returned.
    """
    try:
        active = service.active_instance()
        entries = [e for e in service.instances() if e.get("crn") == active]
    except Exception as exc:
        return _plan_undetermined(
            f"{type(exc).__name__} while listing instances",
            input_fn,
            {"plan": None, "pricing_type": None},
        )

    if len(entries) != 1:
        return _plan_undetermined(
            f"{len(entries)} instance entries match the active instance",
            input_fn,
            {"plan": None, "pricing_type": None},
        )

    entry = entries[0]
    plan = entry.get("plan")
    pricing_type = entry.get("pricing_type")
    reported = {
        "plan": plan if isinstance(plan, str) else None,
        "pricing_type": pricing_type if isinstance(pricing_type, str) else None,
    }

    if plan is not None and plan != REQUIRED_PLAN:
        raise CollectionAborted(
            f"Refusing: the active instance's plan is {plan!r}, not {REQUIRED_PLAN!r}."
        )
    if pricing_type is not None and pricing_type != REQUIRED_PRICING_TYPE:
        raise CollectionAborted(
            f"Refusing: the active instance's pricing type is {pricing_type!r}, "
            f"not {REQUIRED_PRICING_TYPE!r}."
        )
    if plan is None or pricing_type is None:
        missing = " and ".join(
            key for key, value in (("plan", plan), ("pricing_type", pricing_type)) if value is None
        )
        return _plan_undetermined(f"{missing} not reported", input_fn, reported)

    print("Open Plan: confirmed")
    return {**reported, "verified_by": "api"}


def check_allowance(service: Any) -> float:
    """Return remaining QPU seconds, aborting if unknown or under the safety minimum."""
    usage = service.usage()
    remaining = usage.get("usage_remaining_seconds") if isinstance(usage, dict) else None
    if not isinstance(remaining, int | float):
        raise CollectionAborted("Refusing: the API did not report the remaining QPU allowance.")
    if remaining < MIN_REMAINING_SECONDS:
        raise CollectionAborted(
            f"Refusing: only {remaining:.0f} s of QPU allowance left "
            f"(minimum {MIN_REMAINING_SECONDS:.0f} s)."
        )
    return float(remaining)


# --- Backend, qubits, circuit ------------------------------------------------------------


def pick_backend(service: Any, name: str | None) -> Any:
    if name:
        backend = service.backend(name)
    else:
        backend = service.least_busy(operational=True, simulator=False)
    if _is_simulator(backend):
        raise CollectionAborted(f"Refusing: {backend.name} is a simulator.")
    return backend


def _is_simulator(backend: Any) -> bool:
    try:
        return bool(backend.configuration().simulator)
    except Exception:
        return False


def readout_errors(backend: Any) -> dict[int, float]:
    """Measurement error per physical qubit from ``backend.target["measure"]``."""
    errors: dict[int, float] = {}
    for qargs, props in backend.target["measure"].items():
        if qargs is None or len(qargs) != 1 or props is None or props.error is None:
            continue
        errors[int(qargs[0])] = float(props.error)
    return errors


def select_lowest_error(errors: dict[int, float], n: int) -> list[int]:
    """The ``n`` qubits with the lowest readout error, returned in ascending qubit order."""
    ranked = sorted(errors, key=lambda q: (errors[q], q))
    return sorted(ranked[:n])


def calibration_utc(backend: Any) -> str | None:
    try:
        updated = backend.properties().last_update_date
    except Exception:
        return None
    return runs.iso_utc(updated) if isinstance(updated, datetime) else None


def rep_delay_seconds(backend: Any) -> float | None:
    for source in (backend, getattr(backend, "configuration", lambda: None)()):
        value = getattr(source, "default_rep_delay", None)
        if isinstance(value, int | float):
            return float(value)
    return None


def estimate_qpu_seconds(shots: int, rep_delay: float | None) -> float:
    """A rough, local estimate of QPU time. IBM bills what the job actually uses."""
    per_shot = (rep_delay if rep_delay is not None else _FALLBACK_REP_DELAY) + 10e-6
    return _ESTIMATE_OVERHEAD_SECONDS + shots * per_shot


def build_circuit(n_qubits: int) -> Any:
    """Hadamard on every qubit, then measure all: logical qubit i -> classical bit i."""
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(n_qubits, name="qrng")
    circuit.h(range(n_qubits))
    circuit.measure_all()
    return circuit


def transpile_to(backend: Any, circuit: Any, physical_qubits: Sequence[int]) -> Any:
    from qiskit.transpiler import generate_preset_pass_manager

    pass_manager = generate_preset_pass_manager(
        optimization_level=OPTIMIZATION_LEVEL,
        backend=backend,
        initial_layout=list(physical_qubits),
    )
    isa = pass_manager.run(circuit)
    layout = list(isa.layout.final_index_layout())
    if layout != list(physical_qubits):
        raise CollectionAborted(
            f"Transpiled layout {layout} does not match the requested qubits {physical_qubits}."
        )
    return isa


@dataclass
class CollectConfig:
    shots: int = DEFAULT_SHOTS
    n_qubits: int = DEFAULT_QUBITS
    backend_name: str | None = None
    select_qubits: bool = True
    physical_qubits: list[int] | None = None
    account: str = field(default_factory=account_name)
    dry_run: bool = False


@dataclass
class Submission:
    backend_name: str
    backend_qubits: int
    physical_qubits: list[int]
    readout_errors: list[float | None]
    selection: dict[str, Any]
    shots: int
    isa_circuit: Any
    gate_counts: dict[str, int]
    rep_delay: float | None
    estimate_seconds: float


def plan_submission(backend: Any, cfg: CollectConfig) -> Submission:
    """Steps 6 and 7 of SPEC.md, Section 6.3: choose qubits, build and transpile."""
    if cfg.shots <= 0:
        raise CollectionAborted("Shots must be positive.")
    total = int(backend.num_qubits)
    errors = readout_errors(backend)

    if cfg.physical_qubits is not None:
        chosen = list(cfg.physical_qubits)
        if len(set(chosen)) != len(chosen) or any(not 0 <= q < total for q in chosen):
            raise CollectionAborted(f"Physical qubits must be distinct and in 0..{total - 1}.")
        method, used, candidates = "explicit", False, total
    elif cfg.select_qubits:
        n = min(cfg.n_qubits, total)
        if len(errors) < n:
            print(f"Only {len(errors)} qubits report a readout error; using all of them.")
            n = len(errors)
        chosen = select_lowest_error(errors, n)
        method, used, candidates = "lowest_readout_error", True, len(errors)
    else:
        chosen = list(range(min(cfg.n_qubits, total)))
        method, used, candidates = "first_n", False, total

    if not chosen:
        raise CollectionAborted("No qubits selected.")
    if cfg.n_qubits > total and cfg.physical_qubits is None:
        print(f"{backend.name} has {total} qubits; using {len(chosen)} instead of {cfg.n_qubits}.")

    isa = transpile_to(backend, build_circuit(len(chosen)), chosen)
    rep_delay = rep_delay_seconds(backend)
    return Submission(
        backend_name=str(backend.name),
        backend_qubits=total,
        physical_qubits=chosen,
        readout_errors=[errors.get(q) for q in chosen],
        selection={
            "used": used,
            "method": method,
            "candidates": candidates,
            "calibration_utc": calibration_utc(backend),
        },
        shots=cfg.shots,
        isa_circuit=isa,
        gate_counts={str(k): int(v) for k, v in isa.count_ops().items()},
        rep_delay=rep_delay,
        estimate_seconds=estimate_qpu_seconds(cfg.shots, rep_delay),
    )


def print_summary(sub: Submission, remaining_seconds: float | None) -> None:
    known = [e for e in sub.readout_errors if e is not None]
    print()
    print(f"Backend:   {sub.backend_name} ({sub.backend_qubits} qubits)")
    print(f"Qubits:    {len(sub.physical_qubits)} ({sub.selection['method']})")
    print(f"           physical {sub.physical_qubits}")
    if known:
        print(
            f"           readout error min {min(known):.4f}, "
            f"mean {sum(known) / len(known):.4f}, max {max(known):.4f}"
        )
    print(f"Shots:     {sub.shots} ({sub.shots * len(sub.physical_qubits)} bits)")
    print(f"Estimate:  ~{sub.estimate_seconds:.0f} s of QPU time (rough; billed on actual use)")
    if remaining_seconds is not None:
        print(f"Allowance: {remaining_seconds:.0f} s remaining")
    print()


def confirm_backend(sub: Submission, input_fn: InputFn) -> None:
    answer = input_fn(
        f"Type the backend name ({sub.backend_name}) to submit, anything else aborts: "
    )
    if answer.strip() != sub.backend_name:
        raise CollectionAborted("Not confirmed. Nothing was submitted.")


# --- Sampler, job, result ----------------------------------------------------------------


def sampler_options(shots: int) -> dict[str, Any]:
    """Every client-side Sampler option, set explicitly. No mitigation, twirling, or DD."""
    return {
        "default_shots": shots,
        "dynamical_decoupling": {
            "enable": False,
            "sequence_type": "XX",
            "extra_slack_distribution": "middle",
            "scheduling_method": "alap",
            "skip_reset_qubits": False,
        },
        "execution": {
            "init_qubits": True,
            "rep_delay": None,  # None = the backend's default_rep_delay, recorded separately.
            "scheduler_timing": False,
            "stretch_values": False,
            "meas_type": "classified",
        },
        "twirling": {
            "enable_gates": False,
            "enable_measure": False,
            "group": "pauli",
            "num_randomizations": "auto",
            "shots_per_randomization": "auto",
            "strategy": "active-accum",
        },
        "max_execution_time": MAX_EXECUTION_SECONDS,
        "simulator": {
            "angle_decimals": 5,
            "layer_noise_model": None,
            "seed_simulator": None,
            "warn_absent": True,
        },
        "experimental": {},
        "environment": {
            "log_level": "WARNING",
            "job_tags": ["qrng-demo"],
            "private": False,
            "max_execution_time": None,
            "image": None,
        },
    }


def make_sampler(backend: Any, options: dict[str, Any]) -> Any:
    """The client-side Sampler that replaces the deprecated ``SamplerV2`` in 0.50+."""
    from qiskit_ibm_runtime.executor_sampler import Sampler

    return Sampler(mode=backend, options=options)


def bits_from_bitarray(bit_array: Any, n_qubits: int, shots: int) -> npt.NDArray[np.uint8]:
    """Convert a ``BitArray`` to ``(shots, n_qubits)`` uint8; column j is classical bit j.

    Qiskit bitstrings are little-endian (in ``"001"`` classical bit 0 is 1), so never index
    them directly; ``to_bool_array(order="little")`` puts classical bit j in column j.
    """
    bits = np.asarray(bit_array.to_bool_array(order="little"), dtype=np.uint8)
    if bits.shape != (shots, n_qubits):
        raise CollectionAborted(
            f"Unexpected result shape {bits.shape}, wanted {(shots, n_qubits)}."
        )
    return bits


def _status_name(status: Any) -> str:
    return str(getattr(status, "name", status)).upper()


def wait_for_job(job: Any, *, sleep: Callable[[float], None], poll_seconds: float) -> str:
    started = time.monotonic()
    while True:
        status = _status_name(job.status())
        elapsed = int(time.monotonic() - started)
        print(f"\r  status: {status:<10} elapsed {elapsed // 60}:{elapsed % 60:02d}", end="")
        sys.stdout.flush()
        if job.in_final_state():
            print()
            return status
        sleep(poll_seconds)


def _job_details(job: Any) -> dict[str, Any]:
    details: dict[str, Any] = {"qpu_seconds": None, "api_timestamps": None}
    try:
        details["qpu_seconds"] = job.usage()
    except Exception as exc:
        print(f"Note: could not read job usage ({type(exc).__name__}).")
    try:
        stamps = job.metrics().get("timestamps")
        if isinstance(stamps, dict):
            details["api_timestamps"] = {str(k): str(v) for k, v in stamps.items()}
    except Exception as exc:
        print(f"Note: could not read job timestamps ({type(exc).__name__}).")
    return details


def quantum_metadata(
    *,
    run_id: str,
    sub: Submission,
    plan: dict[str, Any],
    job_id: str,
    submitted: datetime,
    completed: datetime,
    details: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": runs.SCHEMA_VERSION,
        "run_id": run_id,
        "created_utc": runs.iso_utc(completed),
        "source": "ibm_quantum_hardware",
        "synthetic": False,
        "backend": {"name": sub.backend_name, "num_qubits": sub.backend_qubits},
        "plan": plan,
        "job": {
            "job_id": job_id,
            "shots": sub.shots,
            "submitted_utc": runs.iso_utc(submitted),
            "completed_utc": runs.iso_utc(completed),
            "api_timestamps": details["api_timestamps"],
            "qpu_seconds": details["qpu_seconds"],
            "estimated_qpu_seconds": round(sub.estimate_seconds, 2),
        },
        "qubits": [
            {"column": column, "physical_qubit": q, "readout_error": err}
            for column, (q, err) in enumerate(
                zip(sub.physical_qubits, sub.readout_errors, strict=True)
            )
        ],
        "qubit_selection": sub.selection,
        "circuit": {
            "description": "H on each qubit, then measure_all; logical qubit i -> classical bit i",
            "optimization_level": OPTIMIZATION_LEVEL,
            "gate_counts": sub.gate_counts,
            "classical_register": "meas",
        },
        "sampler": {
            "class": "qiskit_ibm_runtime.executor_sampler.Sampler",
            "execution_mode": "job",
            "options": options,
            "backend_default_rep_delay_seconds": sub.rep_delay,
            "readout_error_mitigation": False,
            "gate_twirling": False,
            "measurement_twirling": False,
            "dynamical_decoupling": False,
        },
        "bits": {
            "file": runs.QUANTUM_NPZ,
            "array": "bits",
            "dtype": "uint8",
            "shape": [sub.shots, len(sub.physical_qubits)],
            "columns": "logical qubit order; column j is physical_qubits[j]",
            "conversion": 'BitArray.to_bool_array(order="little")',
        },
        "software": runs.software_versions(),
    }


def _validated_options(shots: int) -> dict[str, Any]:
    from qiskit_ibm_runtime.options_models import SamplerOptions

    options = sampler_options(shots)
    dumped: dict[str, Any] = SamplerOptions(**options).model_dump(mode="json")
    if dumped != options:
        raise CollectionAborted("Sampler options changed shape; update sampler_options().")
    return options


# --- The task ----------------------------------------------------------------------------


def dry_run(cfg: CollectConfig) -> int:
    """Steps 5 to 8 against a local fake backend: no account, no network, writes nothing."""
    from qiskit_ibm_runtime import fake_provider

    backend = getattr(fake_provider, DRY_RUN_BACKEND)()
    print(f"DRY RUN against local fake backend {backend.name}. No account, no network.")
    sub = plan_submission(backend, cfg)
    _validated_options(cfg.shots)
    print_summary(sub, None)
    print("Dry run: nothing submitted, nothing written.")
    return 0


def collect_quantum(
    cfg: CollectConfig,
    *,
    service_factory: Callable[[str], Any] | None = None,
    sampler_factory: Callable[[Any, dict[str, Any]], Any] | None = None,
    input_fn: InputFn = input,
    is_interactive: Callable[[], bool] = lambda: sys.stdin.isatty(),
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = POLL_SECONDS,
    runs_dir: Path = RUNS_DIR,
) -> Path:
    """Run SPEC.md, Section 6.3, steps 1 to 9. Returns the new run folder."""
    # Resolved at call time (not as defaults) so tests can patch the module-level functions.
    service_factory = service_factory or load_service
    sampler_factory = sampler_factory or make_sampler
    if not is_interactive():
        raise CollectionAborted(
            "Refusing: collect-quantum must be run from an interactive terminal."
        )

    options = _validated_options(cfg.shots)
    print(f"Loading saved account {cfg.account!r} ...")
    service = service_factory(cfg.account)
    plan = check_open_plan(service, input_fn)
    remaining = check_allowance(service)

    backend = pick_backend(service, cfg.backend_name)
    sub = plan_submission(backend, cfg)
    print_summary(sub, remaining)
    confirm_backend(sub, input_fn)

    sampler = sampler_factory(backend, options)
    submitted = runs.utc_now()
    job = sampler.run([sub.isa_circuit], shots=sub.shots)
    job_id = str(job.job_id())
    print(f"Submitted. Job ID: {job_id}")

    try:
        status = wait_for_job(job, sleep=sleep, poll_seconds=poll_seconds)
    except KeyboardInterrupt:
        raise CollectionAborted(
            f"Stopped waiting. Job {job_id} is still on IBM's side; nothing was written."
        ) from None
    if status != "DONE":
        message = ""
        with contextlib.suppress(Exception):
            message = f": {redact(str(job.error_message()))}"
        raise CollectionAborted(f"Job {job_id} ended as {status}{message}. Nothing was written.")

    completed = runs.utc_now()
    result = job.result()
    bits = bits_from_bitarray(result[0].data.meas, len(sub.physical_qubits), sub.shots)

    run_id = runs.make_run_id(submitted, sub.backend_name)
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(run_dir / runs.QUANTUM_NPZ, bits=bits)
    runs.write_json(
        run_dir / runs.QUANTUM_JSON,
        quantum_metadata(
            run_id=run_id,
            sub=sub,
            plan=plan,
            job_id=job_id,
            submitted=submitted,
            completed=completed,
            details=_job_details(job),
            options=options,
        ),
    )
    print(f"Wrote {run_dir / runs.QUANTUM_NPZ} and {runs.QUANTUM_JSON}")

    classical.collect_for_folder(run_dir)
    print(f"Wrote matching {runs.CLASSICAL_NPZ} and {runs.CLASSICAL_JSON}")
    runs.warn_if_large(run_dir)
    print(f"Run folder: data/runs/{run_id}")
    return run_dir


def friendly_error(exc: BaseException, account: str) -> str:
    """A short, redacted message for network, authentication, and account failures."""
    from qiskit_ibm_runtime.accounts.exceptions import AccountsError
    from qiskit_ibm_runtime.api.exceptions import AuthenticationLicenseError, RequestsApiError
    from qiskit_ibm_runtime.exceptions import IBMError, IBMNotAuthorizedError
    from requests.exceptions import RequestException

    status = getattr(exc, "status_code", None)
    if isinstance(exc, AccountsError):
        return (
            f"Could not load the saved account {account!r}. Check it exists on this Mac "
            f"(README, 'IBM Quantum account'), or set {ACCOUNT_ENV}."
        )
    if isinstance(exc, IBMNotAuthorizedError | AuthenticationLicenseError) or status in (401, 403):
        return "IBM Quantum rejected the credentials. Check the saved account (README)."
    if isinstance(exc, RequestException | ConnectionError | TimeoutError | RequestsApiError):
        return (
            "Could not reach IBM Quantum (network problem). Check your connection and try again. "
            f"[{type(exc).__name__}]"
        )
    if isinstance(exc, IBMError):
        return f"IBM Quantum error ({type(exc).__name__}): {redact(str(exc))}"
    return f"Unexpected error ({type(exc).__name__}): {redact(str(exc))}"


def run_task(cfg: CollectConfig, **kwargs: Any) -> int:
    """Entry point used by ``pipeline.tasks``: never shows a raw traceback."""
    try:
        if cfg.dry_run:
            return dry_run(cfg)
        collect_quantum(cfg, **kwargs)
    except CollectionAborted as exc:
        print(f"\n{redact(str(exc))}")
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"\n{friendly_error(exc, cfg.account)}")
        return 1
    return 0
