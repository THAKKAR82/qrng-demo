"""Real IBM Quantum collection (SPEC.md, Sections 5.2 and 6.3). Run by the human only.

Nothing here runs at import time, and ``qiskit_ibm_runtime`` is imported only inside the
functions that need it. The account is loaded by saved-account *name*; this module never
handles tokens or CRNs, and it redacts anything CRN- or token-like from error messages.

Tests drive every step with a mocked service, backend, and Sampler.
"""

from __future__ import annotations

import contextlib
import copy
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from pipeline import classical, runs
from pipeline.paths import RUNS_DIR, SCRATCH_DATA_DIR

ACCOUNT_ENV = "QRNG_IBM_ACCOUNT"
DEFAULT_ACCOUNT = "qrng-open"
DEFAULT_QUBITS = 100
DEFAULT_SHOTS = 2_000
OPTIMIZATION_LEVEL = 1
MIN_REMAINING_SECONDS = 60.0
MAX_EXECUTION_SECONDS = 300
POLL_SECONDS = 5.0
DRY_RUN_BACKEND = "FakeFez"
PENDING_DIR = SCRATCH_DATA_DIR / "pending"

REQUIRED_PLAN = "open"
REQUIRED_PRICING_TYPE = "free"
OPEN_PLAN_PHRASE = "open plan"

# Rough per-job overhead used only for the pre-submission estimate shown to the human.
_ESTIMATE_OVERHEAD_SECONDS = 2.0
_FALLBACK_REP_DELAY = 250e-6

_CRN_RE = re.compile(r"crn:[^\s'\"),;]*", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{32,}")
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

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
    from_job: str | None = None


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


def sampler_options(
    shots: int,
    *,
    max_execution_time: int = MAX_EXECUTION_SECONDS,
    job_tags: Sequence[str] = ("qrng-demo",),
) -> dict[str, Any]:
    """Every client-side Sampler option, set explicitly. No mitigation, twirling, or DD.

    Live runs (``pipeline.live``) change only the execution limit and the job tags.
    """
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
        "max_execution_time": max_execution_time,
        "simulator": {
            "angle_decimals": 5,
            "layer_noise_model": None,
            "seed_simulator": None,
            "warn_absent": True,
        },
        "experimental": {},
        "environment": {
            "log_level": "WARNING",
            "job_tags": list(job_tags),
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
        # Check finality before reading the status, so a job finishing between the two
        # calls can't return a stale non-final status.
        final = job.in_final_state()
        status = _status_name(job.status())
        elapsed = int(time.monotonic() - started)
        print(f"\r  status: {status:<10} elapsed {elapsed // 60}:{elapsed % 60:02d}", end="")
        sys.stdout.flush()
        if final:
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


class JobFailed(CollectionAborted):
    """The job itself ended in a non-DONE state; there is nothing to recover."""


def _sampler_record(options: dict[str, Any] | None, rep_delay: float | None) -> dict[str, Any]:
    known = options is not None
    return {
        "class": "qiskit_ibm_runtime.executor_sampler.Sampler",
        "execution_mode": "job",
        "options": options,
        "backend_default_rep_delay_seconds": rep_delay,
        "readout_error_mitigation": False if known else None,
        "gate_twirling": False if known else None,
        "measurement_twirling": False if known else None,
        "dynamical_decoupling": False if known else None,
    }


def _base_record(
    *,
    run_id: str,
    source: str,
    backend: dict[str, Any],
    plan: dict[str, Any],
    job: dict[str, Any],
    qubits: list[dict[str, Any]],
    selection: dict[str, Any],
    gate_counts: dict[str, int] | None,
    sampler: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": runs.SCHEMA_VERSION,
        "run_id": run_id,
        "created_utc": None,
        "source": source,
        "synthetic": source != "ibm_quantum_hardware",
        "recovered": False,
        "recovery": None,
        "backend": backend,
        "plan": plan,
        "job": job,
        "qubits": qubits,
        "qubit_selection": selection,
        "circuit": {
            "description": "H on each qubit, then measure_all; logical qubit i -> classical bit i",
            "optimization_level": OPTIMIZATION_LEVEL,
            "gate_counts": gate_counts,
            "classical_register": "meas",
        },
        "sampler": sampler,
        "bits": {
            "file": runs.QUANTUM_NPZ,
            "array": "bits",
            "dtype": "uint8",
            "shape": [job["shots"], len(qubits)],
            "columns": "logical qubit order; column j is physical_qubits[j]",
            "conversion": 'BitArray.to_bool_array(order="little")',
        },
        "software": runs.software_versions(),
    }


def submission_record(
    *,
    sub: Submission,
    plan: dict[str, Any],
    job_id: str,
    submitted: datetime,
    options: dict[str, Any],
    source: str = "ibm_quantum_hardware",
) -> dict[str, Any]:
    """Everything known at submission time. Saved as the pending record, completed later."""
    return _base_record(
        run_id=runs.make_run_id(submitted, sub.backend_name),
        source=source,
        backend={"name": sub.backend_name, "num_qubits": sub.backend_qubits},
        plan=plan,
        job={
            "job_id": job_id,
            "shots": sub.shots,
            "submitted_utc": runs.iso_utc(submitted),
            "completed_utc": None,
            "api_timestamps": None,
            "qpu_seconds": None,
            "estimated_qpu_seconds": round(sub.estimate_seconds, 2),
        },
        qubits=[
            {"column": column, "physical_qubit": q, "readout_error": err}
            for column, (q, err) in enumerate(
                zip(sub.physical_qubits, sub.readout_errors, strict=True)
            )
        ],
        selection=sub.selection,
        gate_counts=sub.gate_counts,
        sampler=_sampler_record(options, sub.rep_delay),
    )


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return moment if moment.tzinfo is not None else moment.astimezone()


def result_bits(job: Any, record: dict[str, Any]) -> npt.NDArray[np.uint8]:
    """The finished job's bits as ``(shots, n_qubits)`` uint8 (SPEC.md, Section 5.2)."""
    result = job.result()
    n_qubits = len(record["qubits"])
    shots = record["job"]["shots"]
    bit_array = result[0].data.meas
    return bits_from_bitarray(bit_array, n_qubits, shots or int(bit_array.num_shots))


def completed_record(
    job: Any, record: dict[str, Any], bits: npt.NDArray[np.uint8]
) -> dict[str, Any]:
    """A copy of the submission ``record`` completed with what the finished job reports."""
    meta = copy.deepcopy(record)
    now = runs.utc_now()
    details = _job_details(job)
    finished = _parse_time((details["api_timestamps"] or {}).get("finished"))
    meta["created_utc"] = runs.iso_utc(now)
    meta["job"]["shots"] = int(bits.shape[0])
    meta["job"]["completed_utc"] = runs.iso_utc(finished or now)
    meta["job"]["api_timestamps"] = details["api_timestamps"]
    meta["job"]["qpu_seconds"] = details["qpu_seconds"]
    meta["bits"]["shape"] = list(bits.shape)
    return meta


def finish_run(
    job: Any,
    record: dict[str, Any],
    *,
    runs_dir: Path,
    sleep: Callable[[float], None],
    poll_seconds: float,
) -> Path:
    """Wait for ``job``, convert its result, and write the complete run folder.

    Shared by normal collection, ``--from-job`` recovery, and the dry run, so all three
    exercise the same result-parsing and writing code. A partly written folder is removed.
    """
    job_id = record["job"]["job_id"]
    status = wait_for_job(job, sleep=sleep, poll_seconds=poll_seconds)
    if status != "DONE":
        message = ""
        with contextlib.suppress(Exception):
            message = f": {redact(str(job.error_message()))}"
        raise JobFailed(f"Job {job_id} ended as {status}{message}. Nothing was written.")

    bits = result_bits(job, record)
    meta = completed_record(job, record, bits)

    run_dir: Path = runs_dir / str(meta["run_id"])
    if run_dir.exists():
        raise CollectionAborted(
            f"{run_dir.name} already exists; run folders are never overwritten."
        )
    run_dir.mkdir(parents=True)
    try:
        np.savez_compressed(run_dir / runs.QUANTUM_NPZ, bits=bits)
        runs.write_json(run_dir / runs.QUANTUM_JSON, meta)
        classical.collect_for_folder(run_dir)
    except BaseException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    print(
        f"Wrote {run_dir.name}/: {runs.QUANTUM_NPZ}, {runs.QUANTUM_JSON}, "
        f"{runs.CLASSICAL_NPZ}, {runs.CLASSICAL_JSON}"
    )
    runs.warn_if_large(run_dir)
    return run_dir


def _validated_options(shots: int, **overrides: Any) -> dict[str, Any]:
    from qiskit_ibm_runtime.options_models import SamplerOptions

    options = sampler_options(shots, **overrides)
    dumped: dict[str, Any] = SamplerOptions(**options).model_dump(mode="json")
    if dumped != options:
        raise CollectionAborted("Sampler options changed shape; update sampler_options().")
    return options


# --- Pending records and recovery --------------------------------------------------------


def _check_job_id(job_id: str) -> str:
    if not _JOB_ID_RE.match(job_id):
        raise CollectionAborted(f"That does not look like a job ID: {job_id!r}")
    return job_id


def save_pending(record: dict[str, Any], pending_dir: Path) -> Path:
    """Keep the submission record locally (gitignored) so ``--from-job`` can rebuild metadata."""
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{_check_job_id(record['job']['job_id'])}.json"
    runs.write_json(path, record)
    return path


def recovery_command(job_id: str) -> str:
    return f"python -m pipeline.tasks collect-quantum --from-job {job_id}"


def _reconstructed_record(job: Any, cfg: CollectConfig, plan: dict[str, Any]) -> dict[str, Any]:
    """Metadata for a job with no local pending record. Unknowns are recorded as ``None``."""
    job_id = str(job.job_id())
    if not cfg.physical_qubits:
        raise CollectionAborted(
            f"No local submission record for job {job_id} (it is kept in data/scratch/pending/ "
            "on the Mac that submitted it). Re-run with --physical-qubits set to the list shown "
            "in that run's summary, in the same order."
        )
    backend = job.backend()
    if backend is None or _is_simulator(backend):
        raise CollectionAborted(f"Job {job_id} did not run on a real backend.")
    errors = readout_errors(backend)
    submitted = _parse_time(job.creation_date) or runs.utc_now()
    return _base_record(
        run_id=runs.make_run_id(submitted, str(backend.name)),
        source="ibm_quantum_hardware",
        backend={"name": str(backend.name), "num_qubits": int(backend.num_qubits)},
        plan=plan,
        job={
            "job_id": job_id,
            "shots": None,
            "submitted_utc": runs.iso_utc(submitted),
            "completed_utc": None,
            "api_timestamps": None,
            "qpu_seconds": None,
            "estimated_qpu_seconds": None,
        },
        qubits=[
            {"column": column, "physical_qubit": q, "readout_error": errors.get(q)}
            for column, q in enumerate(cfg.physical_qubits)
        ],
        selection={
            "used": None,
            "method": "unknown_recovered",
            "candidates": None,
            "calibration_utc": calibration_utc(backend),
            "note": "Reconstructed at recovery: qubits from --physical-qubits; readout errors "
            "from the calibration current at recovery time, not at submission.",
        },
        gate_counts=None,
        sampler=_sampler_record(None, rep_delay_seconds(backend)),
    )


def recover_from_job(
    cfg: CollectConfig,
    *,
    service_factory: Callable[[str], Any] | None = None,
    input_fn: InputFn = input,
    is_interactive: Callable[[], bool] = lambda: sys.stdin.isatty(),
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = POLL_SECONDS,
    runs_dir: Path = RUNS_DIR,
    pending_dir: Path = PENDING_DIR,
) -> Path:
    """Write the run folder for an already-submitted job. Submits nothing."""
    service_factory = service_factory or load_service
    job_id = _check_job_id(cfg.from_job or "")
    if not is_interactive():
        raise CollectionAborted("Refusing: --from-job must be run from an interactive terminal.")

    pending_path = pending_dir / f"{job_id}.json"
    print(f"Loading saved account {cfg.account!r} ...")
    service = service_factory(cfg.account)
    print(f"Retrieving job {job_id}. Nothing new will be submitted.")
    job = service.job(job_id)

    if pending_path.is_file():
        record = runs.read_json(pending_path)
        if record["job"]["job_id"] != job_id:
            raise CollectionAborted(f"{pending_path.name} does not belong to job {job_id}.")
        how = "local pending record"
    else:
        print("No local submission record; reconstructing metadata from the job.")
        record = _reconstructed_record(job, cfg, check_open_plan(service, input_fn))
        how = "reconstructed"
    record["recovered"] = True
    record["recovery"] = {
        "recovered_utc": runs.iso_utc(runs.utc_now()),
        "submission_record": how,
    }

    run_dir = finish_run(job, record, runs_dir=runs_dir, sleep=sleep, poll_seconds=poll_seconds)
    pending_path.unlink(missing_ok=True)
    print(f"Recovered run folder: data/runs/{run_dir.name}")
    return run_dir


# --- Dry run -----------------------------------------------------------------------------


def local_simulator(fake_backend: Any) -> Any:
    """Aer simulator with the fake backend's target, readout and gate errors (no T1/T2).

    Dropping thermal relaxation keeps the noise stabilizer-compatible, so 100+ qubits
    simulate in about a second instead of exhausting memory.
    """
    from qiskit_aer import AerSimulator
    from qiskit_aer.noise import NoiseModel

    noise = NoiseModel.from_backend(
        fake_backend, thermal_relaxation=False, gate_error=True, readout_error=True
    )
    return AerSimulator.from_backend(fake_backend, noise_model=noise, method="stabilizer")


def make_local_sampler(simulator: Any, options: dict[str, Any]) -> Any:
    """The same client-side Sampler as real runs, but only ever on a local Aer simulator."""
    from qiskit_aer import AerSimulator
    from qiskit_ibm_runtime.executor_sampler import Sampler

    if not isinstance(simulator, AerSimulator):
        raise CollectionAborted("The dry run must use a local Aer simulator.")
    return Sampler(mode=simulator, options=options)


def dry_run(cfg: CollectConfig, *, poll_seconds: float = 0.2) -> int:
    """Plan against a fake backend, then run the real Sampler locally and parse and write the
    result into a temporary folder. No account, no network, nothing kept."""
    from qiskit_ibm_runtime import fake_provider

    try:
        import qiskit_aer  # noqa: F401
    except ImportError:
        raise CollectionAborted(
            "The dry run needs qiskit-aer: pip install -r requirements-dev.txt"
        ) from None

    fake = getattr(fake_provider, DRY_RUN_BACKEND)()
    print(f"DRY RUN against local fake backend {fake.name}. No account, no network.")
    options = _validated_options(cfg.shots)
    sub = plan_submission(fake, cfg)
    print_summary(sub, None)

    sampler = make_local_sampler(local_simulator(fake), options)
    job = sampler.run([sub.isa_circuit], shots=sub.shots)
    print(f"Running locally on Aer (simulated, not hardware). Local job ID: {job.job_id()}")
    record = submission_record(
        sub=sub,
        plan={"plan": None, "pricing_type": None, "verified_by": "not_checked_dry_run"},
        job_id=str(job.job_id()),
        submitted=runs.utc_now(),
        options=options,
        source="local_simulator_dry_run",
    )
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = finish_run(
            job, record, runs_dir=Path(tmp), sleep=time.sleep, poll_seconds=poll_seconds
        )
        with np.load(run_dir / runs.QUANTUM_NPZ) as data:
            p_one = data["bits"].mean(axis=0)
        print(
            f"Simulated P(1) per qubit: min {p_one.min():.3f}, mean {p_one.mean():.3f}, "
            f"max {p_one.max():.3f}"
        )
    print("Dry run complete: nothing submitted to IBM, nothing written to data/runs/.")
    return 0


# --- Real collection ---------------------------------------------------------------------


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
    pending_dir: Path = PENDING_DIR,
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
        record = submission_record(
            sub=sub, plan=plan, job_id=job_id, submitted=submitted, options=options
        )
        pending_path = save_pending(record, pending_dir)
        run_dir = finish_run(job, record, runs_dir=runs_dir, sleep=sleep, poll_seconds=poll_seconds)
    except JobFailed:
        raise
    except KeyboardInterrupt:
        print(
            f"\nStopped waiting. The job continues on IBM's side. Recover it with:\n"
            f"  {recovery_command(job_id)}"
        )
        raise CollectionAborted("No run folder was written.") from None
    except Exception as exc:
        print(
            f"\nThe job was submitted but the run could not be written: "
            f"{friendly_error(exc, cfg.account)}"
        )
        print(
            f"Nothing is lost; the results stay on IBM's side. Recover them with:\n"
            f"  {recovery_command(job_id)}"
        )
        raise CollectionAborted("No run folder was written.") from None

    pending_path.unlink(missing_ok=True)
    print(f"Run folder: data/runs/{run_dir.name}")
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
        if cfg.from_job:
            kwargs.pop("sampler_factory", None)
            recover_from_job(cfg, **kwargs)
        else:
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
