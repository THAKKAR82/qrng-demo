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


def min_entropy_from_accuracy(p_guess: float) -> float:
    """``H∞ = -log2(p_guess)`` in bits per bit, capped at 1 bit.

    For a binary guess, accuracy below 0.5 is sampling noise (flipping every guess would
    beat 0.5), so anything at or below 0.5, including 0, gives the coin-flip value of 1 bit.
    """
    if math.isnan(p_guess) or not 0.0 <= p_guess <= 1.0:
        raise ValueError(f"p_guess must be a probability, got {p_guess!r}")
    if p_guess <= 0.5:
        return 1.0
    return -math.log2(p_guess) + 0.0  # + 0.0 turns -0.0 into 0.0 at p_guess = 1


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n > 0, got {successes}/{n}")
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


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
    1 is a white pixel and 0 is black, or however the viewer chooses to draw them.
    """
    flat = _as_bits(bits).reshape(-1)
    needed = size * size
    if size <= 0 or flat.size < needed:
        raise ValueError(f"need {needed} bits for a {size}x{size} bitmap, have {flat.size}")
    return flat[:needed].reshape(size, size)
