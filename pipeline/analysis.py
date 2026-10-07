"""Statistics on bit streams. See SPEC.md, Sections 2, 3 and 3.2.

Nothing here alters the bits: no debiasing, filtering, or mitigation. Qubits flagged as
biased are reported alongside every other qubit, never removed (SPEC.md, Section 4.6).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import stats

Z_95 = 1.959963984540054  # two-sided 95% normal quantile


def _as_bits(bits: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    arr = np.asarray(bits)
    if arr.size == 0:
        raise ValueError("bit array is empty")
    if not np.isin(arr, (0, 1)).all():
        raise ValueError("bit array must contain only 0 and 1")
    return arr.astype(np.uint8, copy=False)


def _as_bits_2d(bits_2d: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    arr = _as_bits(bits_2d)
    if arr.ndim != 2:
        raise ValueError(f"expected a (shots, qubits) array, got shape {arr.shape}")
    return arr


def binary_entropy(p: float) -> float:
    """``h(p) = -p log2 p - (1-p) log2 (1-p)``, with ``h(0) = h(1) = 0``."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def shannon_entropy_per_bit(bits: npt.ArrayLike) -> float:
    """Per-bit Shannon entropy ``h(p̂)`` from the fraction of ones, pooled over all bits."""
    return binary_entropy(float(_as_bits(bits).mean()))


def per_qubit_shannon_entropy(bits_2d: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """``h(p̂_j)`` for each column of a ``(shots, qubits)`` array."""
    p_one = bias_per_qubit(bits_2d)
    return np.array([binary_entropy(float(p)) for p in p_one], dtype=np.float64)


def entropy_estimator_bias(n_samples: int) -> float:
    """Expected downward bias of the plug-in estimate ``h(p̂)`` for a fair coin.

    Expanding ``h`` around 0.5 gives ``h(p̂) ≈ 1 - 2(p̂ - 0.5)² / ln 2``. For a fair coin
    ``E[(p̂ - 0.5)²] = 1 / (4n)``, so ``E[h(p̂)] ≈ 1 - 1 / (2n ln 2)``: even a perfect coin
    measured ``n`` times reads low by about this much (the Miller-Madow correction).
    """
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    return 1.0 / (2.0 * n_samples * math.log(2))


def min_entropy_from_accuracy(p_guess: float) -> float:
    """``H∞ = -log2(max(a, 1 - a))`` in bits per bit, for binary-guess accuracy ``a``.

    An attacker who is reliably wrong is as good as one who is reliably right: flipping
    every guess turns accuracy ``a`` into ``1 - a``. So accuracy 0 and 1 both give 0 bits,
    and 0.5 gives the coin-flip maximum of 1 bit.
    """
    if math.isnan(p_guess) or not 0.0 <= p_guess <= 1.0:
        raise ValueError(f"p_guess must be a probability, got {p_guess!r}")
    return -math.log2(max(p_guess, 1.0 - p_guess)) + 0.0  # + 0.0 turns -0.0 into 0.0


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n > 0, got {successes}/{n}")
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    # At 0 or n successes the exact bound is 0 or 1; rounding would leave it a hair inside.
    low = 0.0 if successes == 0 else max(0.0, center - half)
    high = 1.0 if successes == n else min(1.0, center + half)
    return low, high


@dataclass(frozen=True)
class ChanceRange:
    """Scores a pure guesser lands in, in ``n`` rounds, with probability ``probability``."""

    rounds: int
    low: int
    high: int
    coverage: float
    probability: float


def chance_range(rounds: int, coverage: float = 0.95) -> ChanceRange:
    """The narrowest score range, symmetric about half, holding at least ``coverage``.

    A pure guesser is right on each round with probability 1/2, independently, so the score
    is Binomial(rounds, 1/2). The range ``[k, rounds - k]`` is widened from the middle until
    the exact binomial probability inside it reaches ``coverage``.
    """
    if rounds <= 0:
        raise ValueError(f"rounds must be positive, got {rounds}")
    if not 0.0 < coverage < 1.0:
        raise ValueError(f"coverage must be between 0 and 1, got {coverage!r}")
    total = 2**rounds
    for low in range(rounds // 2, -1, -1):
        high = rounds - low
        inside = sum(math.comb(rounds, k) for k in range(low, high + 1))
        if inside / total >= coverage:
            return ChanceRange(rounds, low, high, coverage, inside / total)
    raise AssertionError("unreachable: the full range has probability 1")


def bias_per_qubit(bits_2d: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """P(1) for each column of a ``(shots, qubits)`` array."""
    p_one: npt.NDArray[np.float64] = _as_bits_2d(bits_2d).mean(axis=0, dtype=np.float64)
    return p_one


@dataclass(frozen=True)
class BiasAnalysis:
    """Per-qubit bias statistics. Every qubit is kept; ``flagged`` only reports."""

    n_shots: int
    p_one: npt.NDArray[np.float64]
    # z of each qubit's P(1) against 0.5, using the binomial SE sqrt(0.25 / shots).
    z_scores: npt.NDArray[np.float64]
    z_threshold: float
    flagged: list[int]
    # Is the spread of per-qubit P(1) larger than shot noise alone predicts?
    chi_square: float
    chi_square_dof: int
    chi_square_p: float
    # Overall mean P(1) against 0.5, treating all bits as independent binomial draws.
    mean_p_one: float
    mean_z: float
    mean_p: float
    # The same question asked across qubits (a t-test on the per-qubit P(1) values). This
    # does not assume every qubit shares one P(1), so it stays honest when they differ.
    across_qubits_t: float
    across_qubits_p: float


def analyze_bias(bits_2d: npt.ArrayLike, z_threshold: float = 3.0) -> BiasAnalysis:
    arr = _as_bits_2d(bits_2d)
    n_shots, n_qubits = arr.shape
    p_one = arr.mean(axis=0, dtype=np.float64)

    z_scores = (p_one - 0.5) / math.sqrt(0.25 / n_shots)
    flagged = [int(j) for j in np.flatnonzero(np.abs(z_scores) > z_threshold)]

    # Chi-square test of homogeneity: under "every qubit has the same P(1) = p̄", each p̂_j
    # has variance p̄(1 - p̄) / shots, so the sum of squared standardized deviations is
    # chi-square with (qubits - 1) degrees of freedom.
    mean_p_one = float(p_one.mean())
    if n_qubits > 1 and 0.0 < mean_p_one < 1.0:
        shot_noise_var = mean_p_one * (1 - mean_p_one) / n_shots
        chi_square = float(np.sum((p_one - mean_p_one) ** 2) / shot_noise_var)
        chi_square_p = float(stats.chi2.sf(chi_square, n_qubits - 1))
    else:
        chi_square, chi_square_p = 0.0, 1.0

    mean_z = (mean_p_one - 0.5) / math.sqrt(0.25 / arr.size)
    mean_p = math.erfc(abs(mean_z) / math.sqrt(2))

    if n_qubits > 1 and float(np.ptp(p_one)) > 0.0:
        t_result = stats.ttest_1samp(p_one, 0.5)
        across_t, across_p = float(t_result.statistic), float(t_result.pvalue)
    else:
        across_t, across_p = math.nan, math.nan

    return BiasAnalysis(
        n_shots=n_shots,
        p_one=p_one,
        z_scores=z_scores,
        z_threshold=z_threshold,
        flagged=flagged,
        chi_square=chi_square,
        chi_square_dof=n_qubits - 1,
        chi_square_p=chi_square_p,
        mean_p_one=mean_p_one,
        mean_z=mean_z,
        mean_p=mean_p,
        across_qubits_t=across_t,
        across_qubits_p=across_p,
    )


def bitmap(bits: npt.ArrayLike, size: int) -> npt.NDArray[np.uint8]:
    """The first ``size * size`` bits, in stream order, as a ``(size, size)`` image.

    A 2D ``(shots, qubits)`` array is flattened shot-major first (SPEC.md, Section 5.2).
    The UI and the notebook draw 1 in the stream's colour and 0 blank (the background).
    """
    flat = _as_bits(bits).reshape(-1)
    needed = size * size
    if size <= 0 or flat.size < needed:
        raise ValueError(f"need {needed} bits for a {size}x{size} bitmap, have {flat.size}")
    return flat[:needed].reshape(size, size)


# A shortfall in per-qubit Shannon entropy is called "noticeable" when it is too large for
# fair coins plus estimator bias to explain at this significance level.
SHORTFALL_ALPHA = 0.01


@dataclass(frozen=True)
class EntropyShortfall:
    """How far the per-qubit mean Shannon entropy sits below 1 bit, and whether fair coins
    could explain it.

    For a fair coin each ``z_j²`` is chi-square with 1 degree of freedom, and
    ``1 - h(p̂_j) ≈ z_j² / (2 n ln 2)``, so the sum of ``z_j²`` over qubits is the right
    test statistic: chi-square with (qubits) degrees of freedom when every qubit is fair.
    """

    mean_entropy: float
    shortfall: float  # 1 - mean_entropy
    estimator_bias: float  # expected shortfall for fair coins, 1 / (2 n ln 2)
    fair_chi_square: float  # sum of z_j² against P(1) = 0.5
    fair_chi_square_dof: int
    fair_chi_square_p: float
    noticeable: bool  # fair_chi_square_p < SHORTFALL_ALPHA


def entropy_shortfall(bits_2d: npt.ArrayLike, alpha: float = SHORTFALL_ALPHA) -> EntropyShortfall:
    arr = _as_bits_2d(bits_2d)
    n_shots, n_qubits = arr.shape
    mean_entropy = float(per_qubit_shannon_entropy(arr).mean())
    z_scores = (arr.mean(axis=0, dtype=np.float64) - 0.5) / math.sqrt(0.25 / n_shots)
    chi_square = float(np.sum(z_scores**2))
    p_value = float(stats.chi2.sf(chi_square, n_qubits))
    return EntropyShortfall(
        mean_entropy=mean_entropy,
        shortfall=1.0 - mean_entropy,
        estimator_bias=entropy_estimator_bias(n_shots),
        fair_chi_square=chi_square,
        fair_chi_square_dof=n_qubits,
        fair_chi_square_p=p_value,
        noticeable=p_value < alpha,
    )


# Which way do the qubits lean? A two-sided sign test on how many qubits read 1 less than
# half the time. Below this p-value the lean has a direction; otherwise it is "mixed".
DIRECTION_ALPHA = 0.01


@dataclass(frozen=True)
class BiasDirection:
    n_below_half: int
    n_above_half: int
    sign_test_p: float
    direction: str  # "toward_0", "toward_1", or "mixed"


def bias_direction(p_one: npt.ArrayLike, alpha: float = DIRECTION_ALPHA) -> BiasDirection:
    p = np.asarray(p_one, dtype=np.float64).reshape(-1)
    below, above = int(np.sum(p < 0.5)), int(np.sum(p > 0.5))
    if below + above == 0:
        return BiasDirection(below, above, 1.0, "mixed")
    p_value = float(stats.binomtest(below, below + above, 0.5).pvalue)
    if p_value >= alpha:
        return BiasDirection(below, above, p_value, "mixed")
    return BiasDirection(below, above, p_value, "toward_0" if below > above else "toward_1")
