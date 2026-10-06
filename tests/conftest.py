from typing import Any

import pytest

from pipeline import quantum


def _forbidden(*_: Any, **__: Any) -> Any:
    raise AssertionError("Tests must never construct a real IBM Quantum service or Sampler.")


@pytest.fixture(autouse=True)
def _no_real_ibm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety net: any test that forgets to inject a mock fails instead of going online."""
    monkeypatch.setattr(quantum, "load_service", _forbidden)
    monkeypatch.setattr(quantum, "make_sampler", _forbidden)
