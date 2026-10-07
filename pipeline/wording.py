"""Comparative phrases for the UI, chosen by rule from measured values (SPEC.md, Section 4.3).

The UI shows these strings verbatim and never chooses comparative words itself. Every rule
is documented in ``ui/src/data/SCHEMA.md`` (``copy``); change both together.
"""

from __future__ import annotations

from dataclasses import dataclass

# Shannon entropy (bits per bit) at or above which a stream "looks equally random".
EQUALLY_RANDOM = 0.99
# ... and at or above which it "looks close to random".
CLOSE_TO_RANDOM = 0.9
# An attacker whose whole interval lies between 0.5 and this is "only slightly" better.
SLIGHTLY_BETTER = 0.55
# Accuracy at or above which an attacker predicted "almost every" bit.
ALMOST_EVERY = 0.99
# Quantum's lowest H∞ this far above classical's highest is "far more" surprise.
FAR_MORE = 0.5
# Mean |P(1) - 0.5| below this is a "slight" lean.
SLIGHT_LEAN = 0.05


@dataclass(frozen=True)
class AttackSummary:
    n_correct: int
    n_predicted: int
    accuracy: float
    ci_low: float
    ci_high: float


def shannon_comparison(classical: float, quantum: float) -> str:
    """``classical`` is the pooled h(p̂); ``quantum`` the per-qubit mean (the honest one)."""
    lead = "By ordinary statistics, "
    if classical >= EQUALLY_RANDOM and quantum >= EQUALLY_RANDOM:
        return lead + "both machines look equally random."
    if classical >= CLOSE_TO_RANDOM and quantum >= CLOSE_TO_RANDOM:
        return lead + "both machines look close to random."
    if classical == quantum:
        return lead + "both machines look equally far from random."
    lower, higher = ("classical", "quantum") if classical < quantum else ("quantum", "classical")
    return lead + f"the {lower} machine looks less random than the {higher} machine."


def attack_phrase(machine: str, result: AttackSummary) -> str:
    """What the attacker managed against one machine, in plain words."""
    if result.n_predicted > 0 and result.n_correct == result.n_predicted:
        return f"The attacker predicted every {machine} bit correctly."
    if result.accuracy >= ALMOST_EVERY:
        return f"The attacker predicted almost every {machine} bit correctly."
    if result.ci_low <= 0.5 <= result.ci_high:
        return f"On the {machine} bits, the attacker did no better than a coin flip."
    if result.ci_low > 0.5 and result.ci_high < SLIGHTLY_BETTER:
        return f"On the {machine} bits, the attacker did only slightly better than a coin flip."
    if result.ci_low > 0.5:
        return (
            f"On the {machine} bits, the attacker did better than a coin flip, but not perfectly."
        )
    return f"On the {machine} bits, the attacker was wrong more often than right."


def unpredictability_comparison(
    classical: tuple[float, float], quantum: tuple[float, float]
) -> str:
    """Each argument is a stream's H∞ range ``(conservative, high)`` in bits per bit."""
    c_low, c_high = classical
    q_low, q_high = quantum
    if q_low - c_high >= FAR_MORE:
        return "Each quantum bit holds far more genuine surprise than each classical bit."
    if q_low > c_high:
        return "Each quantum bit holds more genuine surprise than each classical bit."
    if c_low > q_high:
        return "Each classical bit holds more genuine surprise than each quantum bit."
    return (
        "Both machines' bits hold about the same genuine surprise, within the measurement's "
        "uncertainty."
    )


def bias_note(direction: str, mean_abs_bias: float) -> str:
    """``direction`` is ``analysis.BiasDirection.direction``."""
    slightly = "slightly " if mean_abs_bias < SLIGHT_LEAN else ""
    if direction == "toward_0":
        return f"Most qubits read 0 {slightly}more often than 1."
    if direction == "toward_1":
        return f"Most qubits read 1 {slightly}more often than 0."
    if direction == "mixed":
        return (
            f"Some qubits lean {slightly}toward 0 and others toward 1, with no overall direction."
        )
    raise ValueError(f"unknown bias direction {direction!r}")
