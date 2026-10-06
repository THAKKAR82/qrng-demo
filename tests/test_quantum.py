"""Collector tests. Everything here uses mocks or local fake backends; nothing goes online."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from qiskit.primitives.containers import BitArray
from qiskit_ibm_runtime.accounts.exceptions import AccountNotFoundError
from qiskit_ibm_runtime.api.exceptions import RequestsApiError
from qiskit_ibm_runtime.exceptions import IBMNotAuthorizedError
from qiskit_ibm_runtime.fake_provider import FakeFez, FakeManilaV2
from qiskit_ibm_runtime.options_models import SamplerOptions
from requests.exceptions import ConnectionError as RequestsConnectionError

from pipeline import classical, quantum, runs
from pipeline.paths import RUNS_DIR
from pipeline.quantum import CollectConfig, CollectionAborted

FAKE_CRN = "crn:v1:bluemix:public:quantum-computing:us-east:a/0123456789abcdef:fedcba98::"
FAKE_TOKEN = "Zx9" + "q" * 41


# --- Helpers -----------------------------------------------------------------------------


class FakeService:
    """Stands in for QiskitRuntimeService. Never touches the network."""

    def __init__(
        self,
        instances: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        backend: Any = None,
    ) -> None:
        self._instances = (
            instances
            if instances is not None
            else [
                {"crn": "crn:other", "plan": "premium", "pricing_type": "paid", "name": "x"},
                {"crn": FAKE_CRN, "plan": "open", "pricing_type": "free", "name": "mine"},
            ]
        )
        self._usage = usage if usage is not None else {"usage_remaining_seconds": 590.0}
        self._backend = backend if backend is not None else FakeFez()
        self.least_busy_kwargs: dict[str, Any] | None = None
        self.stored_job: FakeJob | None = None
        self.retrieved: str | None = None

    def active_instance(self) -> str:
        return FAKE_CRN

    def instances(self) -> list[dict[str, Any]]:
        return self._instances

    def usage(self) -> dict[str, Any]:
        return self._usage

    def least_busy(self, **kwargs: Any) -> Any:
        self.least_busy_kwargs = kwargs
        return self._backend

    def backend(self, name: str) -> Any:
        assert name == self._backend.name
        return self._backend

    def job(self, job_id: str) -> Any:
        self.retrieved = job_id
        assert self.stored_job is not None, "no job stored"
        return self.stored_job


class FakeJob:
    def __init__(
        self,
        bits: np.ndarray[Any, Any],
        statuses: list[str] | None = None,
        backend: Any = None,
    ) -> None:
        self._bits = bits
        self._statuses = iter(statuses or ["QUEUED", "RUNNING", "DONE"])
        self._status = "INITIALIZING"
        self._backend = backend
        self.creation_date = "2026-10-05T10:00:00Z"

    def backend(self) -> Any:
        return self._backend

    def job_id(self) -> str:
        return "d3fakejob0000000000"

    def status(self) -> str:
        self._status = next(self._statuses, self._status)
        return self._status

    def in_final_state(self) -> bool:
        return self._status in {"DONE", "ERROR", "CANCELLED"}

    def error_message(self) -> str:
        return f"failed on {FAKE_CRN}"

    def result(self) -> list[Any]:
        bit_array = BitArray.from_bool_array(self._bits.astype(bool), order="little")
        return [SimpleNamespace(data=SimpleNamespace(meas=bit_array))]

    def usage(self) -> float:
        return 2.0

    def metrics(self) -> dict[str, Any]:
        return {
            "timestamps": {"created": "2026-10-05T10:00:00Z", "finished": "2026-10-05T10:01:30Z"},
            "usage": {},
        }


class FakeSampler:
    def __init__(self, backend: Any, options: dict[str, Any], statuses: list[str] | None) -> None:
        self.backend = backend
        self.options = options
        self.statuses = statuses
        self.calls: list[tuple[Any, int]] = []
        self.bits: np.ndarray[Any, Any] | None = None

    def run(self, pubs: list[Any], *, shots: int) -> FakeJob:
        (circuit,) = pubs
        self.calls.append((circuit, shots))
        rng = np.random.default_rng(1)
        self.bits = (rng.random((shots, circuit.num_clbits)) < 0.45).astype(np.uint8)
        return FakeJob(self.bits, self.statuses)


def answers(*replies: str) -> Any:
    it: Iterator[str] = iter(replies)
    prompts: list[str] = []

    def _input(prompt: str) -> str:
        prompts.append(prompt)
        return next(it)

    _input.prompts = prompts  # type: ignore[attr-defined]
    return _input


def no_input(prompt: str) -> str:
    raise AssertionError(f"Unexpected prompt: {prompt}")


# --- Bit order ---------------------------------------------------------------------------


def test_bitarray_little_endian_hand_example() -> None:
    # Qiskit bitstrings are little-endian: in "001" the rightmost char is classical bit 0.
    bit_array = BitArray.from_samples(["001", "110", "100"], num_bits=3)
    bits = quantum.bits_from_bitarray(bit_array, n_qubits=3, shots=3)
    assert bits.dtype == np.uint8
    assert bits.tolist() == [
        [1, 0, 0],  # "001": classical bit 0 = 1
        [0, 1, 1],  # "110": bits 1 and 2 set
        [0, 0, 1],  # "100": classical bit 2 = 1
    ]


def test_flattening_is_shot_major() -> None:
    bit_array = BitArray.from_samples(["001", "110"], num_bits=3)
    bits = quantum.bits_from_bitarray(bit_array, n_qubits=3, shots=2)
    assert bits.reshape(-1).tolist() == [1, 0, 0, 0, 1, 1]


def test_bits_shape_is_checked() -> None:
    bit_array = BitArray.from_samples(["001", "110"], num_bits=3)
    with pytest.raises(CollectionAborted):
        quantum.bits_from_bitarray(bit_array, n_qubits=3, shots=5)


# --- Open Plan guard ---------------------------------------------------------------------


def test_open_plan_confirmed_by_api(capsys: pytest.CaptureFixture[str]) -> None:
    record = quantum.check_open_plan(FakeService(), no_input)
    assert record == {"plan": "open", "pricing_type": "free", "verified_by": "api"}
    out = capsys.readouterr().out
    assert "Open Plan: confirmed" in out
    assert "crn" not in out.lower()
    assert "mine" not in out


@pytest.mark.parametrize(
    ("plan", "pricing_type"),
    [
        ("premium", "paid"),
        ("open", "paid"),
        ("premium", "free"),
        ("Open", "free"),
        ("open", "Free"),
        ("open ", "free"),
        ("open", "trial"),
        ("premium", None),
        (None, "paid"),
        (1, "free"),
    ],
)
def test_non_open_plan_is_refused_without_prompt(plan: Any, pricing_type: Any) -> None:
    entry = {"crn": FAKE_CRN, "plan": plan, "pricing_type": pricing_type}
    with pytest.raises(CollectionAborted, match="Refusing"):
        quantum.check_open_plan(FakeService(instances=[entry]), no_input)


@pytest.mark.parametrize(
    "instances",
    [
        [{"crn": FAKE_CRN, "plan": "open"}],  # pricing_type missing
        [{"crn": FAKE_CRN, "pricing_type": "free"}],  # plan missing
        [{"crn": "crn:someone-else", "plan": "open", "pricing_type": "free"}],  # no match
        [],
    ],
)
def test_undeterminable_plan_requires_typed_confirmation(instances: list[dict[str, Any]]) -> None:
    service = FakeService(instances=instances)
    typed = answers("open plan")
    record = quantum.check_open_plan(service, typed)
    assert record["verified_by"] == "human_typed_open_plan"
    assert "open plan" in typed.prompts[0]

    with pytest.raises(CollectionAborted, match="not confirmed"):
        quantum.check_open_plan(service, answers("yes"))


def test_undeterminable_when_api_call_fails() -> None:
    service = FakeService()

    def boom() -> list[dict[str, Any]]:
        raise RequestsApiError(f"500 for {FAKE_CRN}")

    service.instances = boom  # type: ignore[method-assign]
    assert quantum.check_open_plan(service, answers(" open plan "))["verified_by"] == (
        "human_typed_open_plan"
    )
    with pytest.raises(CollectionAborted):
        quantum.check_open_plan(service, answers("Open Plan"))


def test_plan_record_never_contains_crn_or_name() -> None:
    record = quantum.check_open_plan(FakeService(), no_input)
    assert FAKE_CRN not in json.dumps(record)
    assert set(record) == {"plan", "pricing_type", "verified_by"}


# --- Allowance ---------------------------------------------------------------------------


@pytest.mark.parametrize("usage", [{}, {"usage_remaining_seconds": None}, {"other": 5}])
def test_allowance_missing_is_refused(usage: dict[str, Any]) -> None:
    with pytest.raises(CollectionAborted, match="did not report"):
        quantum.check_allowance(FakeService(usage=usage))


def test_low_allowance_is_refused() -> None:
    with pytest.raises(CollectionAborted, match="only 59 s"):
        quantum.check_allowance(FakeService(usage={"usage_remaining_seconds": 59}))
    assert quantum.check_allowance(FakeService(usage={"usage_remaining_seconds": 60})) == 60.0


# --- Qubits and circuit ------------------------------------------------------------------


def test_select_lowest_error() -> None:
    errors = {0: 0.05, 1: 0.01, 2: 0.03, 3: 0.01, 4: 0.2}
    assert quantum.select_lowest_error(errors, 3) == [1, 2, 3]


def test_plan_submission_selects_lowest_readout_error() -> None:
    backend = FakeFez()
    errors = quantum.readout_errors(backend)
    sub = quantum.plan_submission(backend, CollectConfig(n_qubits=10, shots=50))
    assert len(sub.physical_qubits) == 10
    assert sub.readout_errors == [errors[q] for q in sub.physical_qubits]
    assert max(errors[q] for q in sub.physical_qubits) <= sorted(errors.values())[9]
    assert sub.selection["used"] is True
    assert sub.selection["method"] == "lowest_readout_error"
    assert sub.selection["candidates"] == len(errors)
    assert sub.selection["calibration_utc"] is not None
    assert list(sub.isa_circuit.layout.final_index_layout()) == sub.physical_qubits
    assert sub.gate_counts["measure"] == 10


def test_default_is_100_qubits_2000_shots() -> None:
    sub = quantum.plan_submission(FakeFez(), CollectConfig())
    assert len(sub.physical_qubits) == 100
    assert sub.shots == 2000


def test_plan_submission_without_selection_uses_first_n() -> None:
    sub = quantum.plan_submission(FakeFez(), CollectConfig(n_qubits=4, select_qubits=False))
    assert sub.physical_qubits == [0, 1, 2, 3]
    assert sub.selection["used"] is False
    assert sub.selection["method"] == "first_n"
    assert all(e is not None for e in sub.readout_errors)


def test_plan_submission_explicit_qubits() -> None:
    sub = quantum.plan_submission(FakeFez(), CollectConfig(physical_qubits=[12, 3, 7]))
    assert sub.physical_qubits == [12, 3, 7]
    assert list(sub.isa_circuit.layout.final_index_layout()) == [12, 3, 7]
    assert sub.selection["method"] == "explicit"
    with pytest.raises(CollectionAborted):
        quantum.plan_submission(FakeFez(), CollectConfig(physical_qubits=[1, 1]))
    with pytest.raises(CollectionAborted):
        quantum.plan_submission(FakeFez(), CollectConfig(physical_qubits=[999]))


def test_plan_submission_caps_at_backend_size() -> None:
    sub = quantum.plan_submission(FakeManilaV2(), CollectConfig(n_qubits=100))
    assert len(sub.physical_qubits) == 5


def test_circuit_is_hadamard_then_measure() -> None:
    circuit = quantum.build_circuit(3)
    ops = [inst.operation.name for inst in circuit.data]
    assert ops == ["h", "h", "h", "barrier", "measure", "measure", "measure"]
    measures = [inst for inst in circuit.data if inst.operation.name == "measure"]
    for i, inst in enumerate(measures):
        assert circuit.find_bit(inst.qubits[0]).index == i
        assert circuit.find_bit(inst.clbits[0]).index == i


# --- Sampler options ---------------------------------------------------------------------


def test_sampler_options_are_explicit_and_complete() -> None:
    options = quantum.sampler_options(2000)
    # Every field of the installed SamplerOptions model is set explicitly (no hidden defaults).
    assert SamplerOptions(**options).model_dump(mode="json") == options
    assert options["twirling"]["enable_gates"] is False
    assert options["twirling"]["enable_measure"] is False
    assert options["dynamical_decoupling"]["enable"] is False
    assert options["execution"]["meas_type"] == "classified"
    assert options["default_shots"] == 2000


# --- Confirmation prompt -----------------------------------------------------------------


def test_confirm_backend_requires_exact_name() -> None:
    sub = quantum.plan_submission(FakeManilaV2(), CollectConfig(n_qubits=2, shots=10))
    quantum.confirm_backend(sub, answers("fake_manila"))
    quantum.confirm_backend(sub, answers("  fake_manila\n"))
    for wrong in ("", "y", "yes", "FAKE_MANILA", "fake_fez"):
        with pytest.raises(CollectionAborted, match="Nothing was submitted"):
            quantum.confirm_backend(sub, answers(wrong))


# --- Full flow with mocks ----------------------------------------------------------------


def _run(
    tmp_path: Path,
    service: FakeService,
    replies: list[str],
    *,
    cfg: CollectConfig | None = None,
    statuses: list[str] | None = None,
    interactive: bool = True,
    sleep: Any = None,
) -> tuple[Path, list[FakeSampler]]:
    samplers: list[FakeSampler] = []

    def sampler_factory(backend: Any, options: dict[str, Any]) -> FakeSampler:
        samplers.append(FakeSampler(backend, options, statuses))
        return samplers[-1]

    run_dir = quantum.collect_quantum(
        cfg or CollectConfig(n_qubits=5, shots=40, account="qrng-open"),
        service_factory=lambda name: service,
        sampler_factory=sampler_factory,
        input_fn=answers(*replies),
        is_interactive=lambda: interactive,
        sleep=sleep or (lambda _: None),
        runs_dir=tmp_path / "runs",
        pending_dir=tmp_path / "pending",
    )
    return run_dir, samplers


def test_full_collection_writes_run_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeService()
    run_dir, samplers = _run(tmp_path, service, ["fake_fez"])

    assert service.least_busy_kwargs == {"operational": True, "simulator": False}
    assert run_dir.parent == tmp_path / "runs"
    assert not list((tmp_path / "pending").iterdir())  # pending record removed on success
    assert run_dir.name.endswith("Z_fake_fez")
    (sampler,) = samplers
    assert sampler.calls[0][1] == 40

    with np.load(run_dir / runs.QUANTUM_NPZ) as data:
        bits = data["bits"]
    assert bits.dtype == np.uint8
    assert bits.shape == (40, 5)
    assert sampler.bits is not None
    assert np.array_equal(bits, sampler.bits)

    meta = runs.read_json(run_dir / runs.QUANTUM_JSON)
    assert meta["synthetic"] is False
    assert meta["recovered"] is False
    assert meta["job"]["completed_utc"] == "2026-10-05T10:01:30Z"
    assert meta["source"] == "ibm_quantum_hardware"
    assert meta["backend"] == {"name": "fake_fez", "num_qubits": 156}
    assert meta["plan"] == {"plan": "open", "pricing_type": "free", "verified_by": "api"}
    assert meta["job"]["job_id"] == "d3fakejob0000000000"
    assert meta["job"]["shots"] == 40
    assert meta["job"]["qpu_seconds"] == 2.0
    assert meta["qubit_selection"]["used"] is True
    assert [q["column"] for q in meta["qubits"]] == [0, 1, 2, 3, 4]
    assert all(isinstance(q["readout_error"], float) for q in meta["qubits"])
    assert meta["sampler"]["options"] == quantum.sampler_options(40)
    assert meta["sampler"]["class"] == "qiskit_ibm_runtime.executor_sampler.Sampler"
    for flag in ("readout_error_mitigation", "gate_twirling", "measurement_twirling"):
        assert meta["sampler"][flag] is False
    assert meta["sampler"]["dynamical_decoupling"] is False

    classical_meta = runs.read_json(run_dir / runs.CLASSICAL_JSON)
    assert classical_meta["matched_bits"] == 200
    assert classical_meta["run_id"] == run_dir.name

    out = capsys.readouterr().out
    assert out.index("Job ID: d3fakejob0000000000") < out.index("status: QUEUED")
    assert "status: DONE" in out
    for text in (out, json.dumps(meta), json.dumps(classical_meta)):
        assert "crn:" not in text
        assert FAKE_TOKEN not in text


def test_named_backend_is_used(tmp_path: Path) -> None:
    service = FakeService(backend=FakeManilaV2())
    cfg = CollectConfig(n_qubits=3, shots=8, backend_name="fake_manila")
    run_dir, _ = _run(tmp_path, service, ["fake_manila"], cfg=cfg)
    assert service.least_busy_kwargs is None
    assert run_dir.name.endswith("_fake_manila")


def test_declined_confirmation_submits_nothing(tmp_path: Path) -> None:
    with pytest.raises(CollectionAborted, match="Nothing was submitted"):
        _run(tmp_path, FakeService(), ["ibm_fez"])
    assert not (tmp_path / "runs").exists()
    assert not (tmp_path / "pending").exists()


def test_non_open_plan_stops_before_backend(tmp_path: Path) -> None:
    service = FakeService(instances=[{"crn": FAKE_CRN, "plan": "premium", "pricing_type": "paid"}])
    with pytest.raises(CollectionAborted, match="Refusing"):
        _run(tmp_path, service, [])
    assert service.least_busy_kwargs is None


def test_non_interactive_refuses_before_loading_account(tmp_path: Path) -> None:
    def service_factory(name: str) -> Any:
        raise AssertionError("account must not be loaded")

    with pytest.raises(CollectionAborted, match="interactive terminal"):
        quantum.collect_quantum(
            CollectConfig(),
            service_factory=service_factory,
            input_fn=no_input,
            is_interactive=lambda: False,
            runs_dir=tmp_path,
        )


def test_failed_job_writes_nothing_and_redacts(tmp_path: Path) -> None:
    with pytest.raises(CollectionAborted) as excinfo:
        _run(tmp_path, FakeService(), ["fake_fez"], statuses=["QUEUED", "ERROR"])
    assert "ERROR" in str(excinfo.value)
    assert "crn:<redacted>" in str(excinfo.value)
    assert FAKE_CRN not in str(excinfo.value)
    assert not (tmp_path / "runs").exists()


# --- Friendly errors ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (AccountNotFoundError("no account"), "Could not load the saved account"),
        (IBMNotAuthorizedError(f"bad token {FAKE_TOKEN}"), "rejected the credentials"),
        (RequestsApiError(f"401 at {FAKE_CRN}", status_code=401), "rejected the credentials"),
        (RequestsApiError(f"503 at {FAKE_CRN}", status_code=503), "network problem"),
        (RequestsConnectionError(f"https://x/{FAKE_CRN}"), "network problem"),
        (RuntimeError(f"weird {FAKE_CRN} {FAKE_TOKEN}"), "Unexpected error"),
    ],
)
def test_run_task_prints_friendly_redacted_message(
    exc: Exception, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    def service_factory(name: str) -> Any:
        raise exc

    code = quantum.run_task(
        CollectConfig(account="qrng-open"),
        service_factory=service_factory,
        is_interactive=lambda: True,
    )
    out = capsys.readouterr()
    assert code == 1
    assert expected in out.out
    assert "Traceback" not in out.out + out.err
    assert FAKE_CRN not in out.out
    assert FAKE_TOKEN not in out.out


def test_redact() -> None:
    text = f"url https://api/{FAKE_CRN}/jobs token={FAKE_TOKEN} job d3fakejob0000000000"
    cleaned = quantum.redact(text)
    assert FAKE_CRN not in cleaned
    assert FAKE_TOKEN not in cleaned
    assert "d3fakejob0000000000" in cleaned


def test_dry_run_runs_real_sampler_locally_and_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # conftest makes load_service and make_sampler raise, so this proves neither is used:
    # the real client-side Sampler runs on a local Aer simulator built from FakeFez.
    before = sorted(RUNS_DIR.iterdir())
    assert quantum.run_task(CollectConfig(n_qubits=5, shots=50, dry_run=True)) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "fake_fez" in out
    assert "status: DONE" in out
    assert "Simulated P(1) per qubit" in out
    assert "nothing submitted to IBM" in out
    assert sorted(RUNS_DIR.iterdir()) == before


def test_local_sampler_refuses_non_simulator() -> None:
    with pytest.raises(CollectionAborted, match="local Aer simulator"):
        quantum.make_local_sampler(FakeFez(), quantum.sampler_options(10))


def test_local_sampler_result_parses_like_hardware(tmp_path: Path) -> None:
    """The real Sampler's run/result path, on Aer, through the shared finish_run writer."""
    fake = FakeFez()
    sub = quantum.plan_submission(fake, CollectConfig(n_qubits=100, shots=2000))
    options = quantum.sampler_options(sub.shots)
    job = quantum.make_local_sampler(quantum.local_simulator(fake), options).run(
        [sub.isa_circuit], shots=sub.shots
    )
    record = quantum.submission_record(
        sub=sub,
        plan={"plan": None, "pricing_type": None, "verified_by": "not_checked_dry_run"},
        job_id=str(job.job_id()),
        submitted=runs.utc_now(),
        options=options,
        source="local_simulator_dry_run",
    )
    run_dir = quantum.finish_run(
        job, record, runs_dir=tmp_path, sleep=lambda _: None, poll_seconds=0
    )
    with np.load(run_dir / runs.QUANTUM_NPZ) as data:
        bits = data["bits"]
    assert bits.shape == (2000, 100)
    assert 0.4 < bits.mean() < 0.6
    meta = runs.read_json(run_dir / runs.QUANTUM_JSON)
    assert meta["synthetic"] is True
    assert meta["source"] == "local_simulator_dry_run"
    assert runs.read_json(run_dir / runs.CLASSICAL_JSON)["matched_bits"] == 200_000


# --- Recovery (--from-job) ---------------------------------------------------------------

JOB_ID = "d3fakejob0000000000"
RECOVERY_HINT = "python -m pipeline.tasks " + "collect-quantum --from-job " + JOB_ID


def _recover(tmp_path: Path, service: FakeService, cfg: CollectConfig) -> Path:
    return quantum.recover_from_job(
        cfg,
        service_factory=lambda name: service,
        input_fn=no_input,
        is_interactive=lambda: True,
        sleep=lambda _: None,
        runs_dir=tmp_path / "runs",
        pending_dir=tmp_path / "pending",
    )


def test_write_failure_prints_recovery_command_then_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def disk_full(folder: Path) -> Any:
        raise OSError(28, "No space left on device")

    real_collect = classical.collect_for_folder
    monkeypatch.setattr(classical, "collect_for_folder", disk_full)
    service = FakeService()
    with pytest.raises(CollectionAborted, match="No run folder was written"):
        _run(tmp_path, service, ["fake_fez"])
    out = capsys.readouterr().out
    assert RECOVERY_HINT in out
    assert list((tmp_path / "runs").iterdir()) == []  # partial folder removed
    pending = tmp_path / "pending" / f"{JOB_ID}.json"
    assert pending.is_file()
    expected_bits = FakeSampler(None, {}, None).run([quantum.build_circuit(5)], shots=40)._bits

    # Recover: same bits, same metadata, plus the recovery fields. Nothing is submitted.
    monkeypatch.setattr(classical, "collect_for_folder", real_collect)
    service.stored_job = FakeJob(expected_bits, ["DONE"])
    run_dir = _recover(tmp_path, service, CollectConfig(from_job=JOB_ID))
    assert service.retrieved == JOB_ID
    with np.load(run_dir / runs.QUANTUM_NPZ) as data:
        assert np.array_equal(data["bits"], expected_bits)
    meta = runs.read_json(run_dir / runs.QUANTUM_JSON)
    assert meta["recovered"] is True
    assert meta["recovery"]["submission_record"] == "local pending record"
    assert meta["plan"]["verified_by"] == "api"
    assert meta["sampler"]["options"] == quantum.sampler_options(40)
    assert meta["qubit_selection"]["method"] == "lowest_readout_error"
    assert meta["job"]["qpu_seconds"] == 2.0
    assert runs.read_json(run_dir / runs.CLASSICAL_JSON)["matched_bits"] == 200
    assert not pending.exists()


def test_interrupt_while_waiting_prints_recovery_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupt(_: float) -> None:
        raise KeyboardInterrupt

    with pytest.raises(CollectionAborted):
        _run(tmp_path, FakeService(), ["fake_fez"], sleep=interrupt)
    assert RECOVERY_HINT in capsys.readouterr().out
    assert (tmp_path / "pending" / f"{JOB_ID}.json").is_file()


def test_failed_job_does_not_suggest_recovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(quantum.JobFailed):
        _run(tmp_path, FakeService(), ["fake_fez"], statuses=["ERROR"])
    assert "--from-job" not in capsys.readouterr().out


def _stored(statuses: list[str]) -> FakeService:
    service = FakeService()
    service.stored_job = FakeJob(np.zeros((8, 3), dtype=np.uint8), statuses, backend=FakeFez())
    return service


def test_recovery_without_pending_record_needs_qubits(tmp_path: Path) -> None:
    service = _stored(["DONE"])
    with pytest.raises(CollectionAborted, match="--physical-qubits"):
        _recover(tmp_path, service, CollectConfig(from_job=JOB_ID))

    run_dir = _recover(
        tmp_path, service, CollectConfig(from_job=JOB_ID, physical_qubits=[12, 3, 7])
    )
    meta = runs.read_json(run_dir / runs.QUANTUM_JSON)
    assert run_dir.name == "2026-10-05T100000Z_fake_fez"
    assert meta["recovered"] is True
    assert meta["recovery"]["submission_record"] == "reconstructed"
    assert [q["physical_qubit"] for q in meta["qubits"]] == [12, 3, 7]
    assert all(isinstance(q["readout_error"], float) for q in meta["qubits"])
    assert meta["qubit_selection"]["method"] == "unknown_recovered"
    assert meta["sampler"]["options"] is None
    assert meta["sampler"]["readout_error_mitigation"] is None
    assert meta["job"]["shots"] == 8
    assert meta["plan"]["verified_by"] == "api"


def test_recovery_rejects_wrong_qubit_count(tmp_path: Path) -> None:
    cfg = CollectConfig(from_job=JOB_ID, physical_qubits=[1, 2])
    with pytest.raises(CollectionAborted, match="Unexpected result shape"):
        _recover(tmp_path, _stored(["DONE"]), cfg)


def test_recovery_refuses_non_interactive_before_loading_account() -> None:
    def service_factory(name: str) -> Any:
        raise AssertionError("account must not be loaded")

    with pytest.raises(CollectionAborted, match="interactive terminal"):
        quantum.recover_from_job(
            CollectConfig(from_job=JOB_ID),
            service_factory=service_factory,
            is_interactive=lambda: False,
        )


def test_recovery_rejects_bad_job_id(tmp_path: Path) -> None:
    with pytest.raises(CollectionAborted, match="job ID"):
        _recover(tmp_path, FakeService(), CollectConfig(from_job="../../etc/passwd"))


def test_recovery_of_failed_job_writes_nothing(tmp_path: Path) -> None:
    cfg = CollectConfig(from_job=JOB_ID, physical_qubits=[1, 2, 3])
    with pytest.raises(quantum.JobFailed):
        _recover(tmp_path, _stored(["CANCELLED"]), cfg)
    assert not (tmp_path / "runs").exists()


def test_recovery_never_overwrites(tmp_path: Path) -> None:
    cfg = CollectConfig(from_job=JOB_ID, physical_qubits=[1, 2, 3])
    _recover(tmp_path, _stored(["DONE"]), cfg)
    with pytest.raises(CollectionAborted, match="never overwritten"):
        _recover(tmp_path, _stored(["DONE"]), cfg)


def test_run_task_from_job_errors_are_friendly(capsys: pytest.CaptureFixture[str]) -> None:
    def service_factory(name: str) -> Any:
        raise RequestsConnectionError(f"https://x/{FAKE_CRN}")

    code = quantum.run_task(
        CollectConfig(from_job=JOB_ID),
        service_factory=service_factory,
        is_interactive=lambda: True,
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "network problem" in out
    assert FAKE_CRN not in out


def test_account_name_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(quantum.ACCOUNT_ENV, raising=False)
    assert quantum.account_name() == "qrng-open"
    monkeypatch.setenv(quantum.ACCOUNT_ENV, "other")
    assert quantum.account_name() == "other"
