import pytest

from pipeline import wording
from pipeline.wording import AttackSummary


@pytest.mark.parametrize(
    ("classical", "quantum", "expected"),
    [
        (0.99, 0.99, "equally random"),
        (0.9999, 0.995, "equally random"),
        (0.99, 0.9899, "close to random"),
        (0.95, 0.999, "close to random"),
        (0.9, 0.9, "close to random"),
        (0.999, 0.85, "the quantum machine looks less random than the classical machine"),
        (0.5, 0.999, "the classical machine looks less random than the quantum machine"),
    ],
)
def test_shannon_comparison(classical: float, quantum: float, expected: str) -> None:
    assert expected in wording.shannon_comparison(classical, quantum)


def _attack(n_correct: int, n: int, low: float, high: float) -> AttackSummary:
    return AttackSummary(n_correct, n, n_correct / n, low, high)


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (_attack(1000, 1000, 0.996, 1.0), "predicted every classical bit"),
        (_attack(995, 1000, 0.98, 0.998), "almost every classical bit"),
        (_attack(500, 1000, 0.47, 0.53), "no better than a coin flip"),
        (_attack(504, 1000, 0.5009, 0.5071), "only slightly better than a coin flip"),
        (_attack(600, 1000, 0.57, 0.63), "better than a coin flip, but not perfectly"),
        (_attack(600, 1000, 0.52, 0.63), "better than a coin flip, but not perfectly"),
        (_attack(400, 1000, 0.37, 0.43), "wrong more often than right"),
    ],
)
def test_attack_phrase(summary: AttackSummary, expected: str) -> None:
    assert expected in wording.attack_phrase("classical", summary)


@pytest.mark.parametrize(
    ("classical", "quantum", "expected"),
    [
        ((0.0, 0.00003), (0.98, 0.997), "far more"),
        ((0.0, 0.5), (0.5001, 0.9), "Each quantum bit holds more"),
        ((0.0, 0.6), (0.5, 0.9), "about the same"),
        ((0.9, 1.0), (0.1, 0.2), "Each classical bit holds more"),
    ],
)
def test_unpredictability_comparison(
    classical: tuple[float, float], quantum: tuple[float, float], expected: str
) -> None:
    assert expected in wording.unpredictability_comparison(classical, quantum)


def test_bias_note() -> None:
    assert wording.bias_note("toward_0", 0.01) == "Most qubits read 0 slightly more often than 1."
    assert wording.bias_note("toward_1", 0.2) == "Most qubits read 1 more often than 0."
    assert "no overall direction" in wording.bias_note("mixed", 0.01)
    with pytest.raises(ValueError):
        wording.bias_note("sideways", 0.01)
