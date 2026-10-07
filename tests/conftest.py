from typing import Any

import pytest
import qiskit_ibm_runtime
import qiskit_ibm_runtime.executor_sampler
import qiskit_ibm_runtime.qiskit_runtime_service
from qiskit_aer import AerSimulator

from pipeline import quantum

_RealSampler = qiskit_ibm_runtime.executor_sampler.Sampler


def _forbidden(*_: Any, **__: Any) -> Any:
    raise AssertionError("Tests must never construct a real IBM Quantum service or Sampler.")


def _local_sampler_only(*args: Any, **kwargs: Any) -> Any:
    """The client-side Sampler, allowed only on a local Aer simulator (the dry run)."""
    mode = kwargs.get("mode", args[0] if args else None)
    if not isinstance(mode, AerSimulator):
        _forbidden()
    return _RealSampler(*args, **kwargs)


@pytest.fixture(autouse=True)
def _no_real_ibm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety net: any test that forgets to inject a mock fails instead of going online.

    The collector's own factories are patched, and so are the library classes behind them,
    so a mocking mistake anywhere (the collector, the live server, an ad-hoc import) fails
    loudly instead of reaching IBM.
    """
    monkeypatch.setattr(quantum, "load_service", _forbidden)
    monkeypatch.setattr(quantum, "make_sampler", _forbidden)
    monkeypatch.setattr(qiskit_ibm_runtime, "QiskitRuntimeService", _forbidden)
    monkeypatch.setattr(
        qiskit_ibm_runtime.qiskit_runtime_service, "QiskitRuntimeService", _forbidden
    )
    for name in ("SamplerV2", "Sampler"):
        if hasattr(qiskit_ibm_runtime, name):
            monkeypatch.setattr(qiskit_ibm_runtime, name, _forbidden)
    monkeypatch.setattr(qiskit_ibm_runtime.executor_sampler, "Sampler", _local_sampler_only)
