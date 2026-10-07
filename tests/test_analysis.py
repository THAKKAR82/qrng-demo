import math

import numpy as np
import pytest

from pipeline.analysis import (
    analyze_bias,
    bias_direction,
    bias_per_qubit,
    bitmap,
    chance_range,
    entropy_estimator_bias,
    entropy_shortfall,
    min_entropy_from_accuracy,
    per_qubit_shannon_entropy,
    shannon_entropy_per_bit,
    wilson_interval,
)

# --- Shannon entropy -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bits", "expected"),
    [
        ([0, 0, 0, 0], 0.0),
        ([1, 1, 1, 1], 0.0),
        ([0, 1, 0, 1], 1.0),
        ([1, 0, 0, 0], 0.8112781244591328),  # h(0.25), by hand
        ([1, 1, 1, 0, 0, 0, 0, 0, 0, 0], 0.8812908992306927),  # h(0.3)
    ],
)
def test_shannon_entropy_of_known_distributions(bits: list[int], expected: float) -> None:
    assert shannon_entropy_per_bit(np.array(bits, dtype=np.uint8)) == pytest.approx(expected)


def test_shannon_entropy_pools_a_2d_array() -> None:
    # Two columns with opposite bias pool to p = 0.5: pooling hides per-qubit bias.
    bits = np.array([[1, 0], [1, 0], [1, 0], [0, 1]], dtype=np.uint8)
    assert shannon_entropy_per_bit(bits) == pytest.approx(1.0)


def test_shannon_entropy_rejects_empty_and_non_binary() -> None:
    with pytest.raises(ValueError):
        shannon_entropy_per_bit(np.array([], dtype=np.uint8))
    with pytest.raises(ValueError):
        shannon_entropy_per_bit(np.array([0, 2, 1]))


# --- Min-entropy -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("p_guess", "expected"),
    [
        (1.0, 0.0),
        (0.5, 1.0),
        (0.75, 0.4150374992788438),
        (0.55, 0.862496476250065),
        # Reliably wrong is as good as reliably right: flip every guess.
        (0.0, 0.0),
        (0.25, 0.4150374992788438),
        (0.45, 0.862496476250065),
    ],
)
def test_min_entropy_from_accuracy(p_guess: float, expected: float) -> None:
    assert min_entropy_from_accuracy(p_guess) == pytest.approx(expected)


@pytest.mark.parametrize("p_guess", [0.0, 1.0])
def test_min_entropy_of_perfect_prediction_is_positive_zero(p_guess: float) -> None:
    assert math.copysign(1.0, min_entropy_from_accuracy(p_guess)) == 1.0


@pytest.mark.parametrize("p_guess", [-0.1, 1.01, math.nan])
def test_min_entropy_rejects_invalid_probabilities(p_guess: float) -> None:
    with pytest.raises(ValueError):
        min_entropy_from_accuracy(p_guess)


# --- Wilson interval -------------------------------------------------------------------------


def test_wilson_interval_at_half() -> None:
    low, high = wilson_interval(50, 100)
    assert low == pytest.approx(0.40383, abs=1e-5)
    assert high == pytest.approx(0.59617, abs=1e-5)


def test_wilson_interval_at_perfect_accuracy() -> None:
    low, high = wilson_interval(100, 100)
    assert low == pytest.approx(100 / (100 + 1.959963984540054**2))
    assert high == 1.0


@pytest.mark.parametrize("n", [1, 100, 180_032, 10**7])
def test_wilson_interval_is_exact_at_the_ends(n: int) -> None:
    # Rounding must not leave the bound a hair inside 0 or 1: at accuracy 1 that would make
    # the conservative H∞ (a tiny positive number) exceed the point estimate (0).
    assert wilson_interval(n, n)[1] == 1.0
    assert wilson_interval(0, n)[0] == 0.0
    assert min_entropy_from_accuracy(wilson_interval(n, n)[1]) == 0.0


def test_wilson_interval_rejects_bad_counts() -> None:
    with pytest.raises(ValueError):
        wilson_interval(5, 0)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


# --- Per-qubit bias --------------------------------------------------------------------------


def test_bias_per_qubit_is_p_one_per_column() -> None:
    bits = np.array([[1, 0], [1, 1], [0, 0], [1, 0]], dtype=np.uint8)
    np.testing.assert_allclose(bias_per_qubit(bits), [0.75, 0.25])


def test_bias_per_qubit_requires_2d() -> None:
    with pytest.raises(ValueError):
        bias_per_qubit(np.array([0, 1, 1], dtype=np.uint8))


def _columns_with_ones(n_shots: int, ones_per_column: list[int]) -> np.ndarray:
    bits = np.zeros((n_shots, len(ones_per_column)), dtype=np.uint8)
    for col, ones in enumerate(ones_per_column):
        bits[:ones, col] = 1
    return bits


def test_analyze_bias_z_scores_and_flags() -> None:
    # n = 100 shots, binomial SE under p = 0.5 is 0.05.
    bits = _columns_with_ones(100, [60, 80, 50, 36, 34])
    result = analyze_bias(bits)
    np.testing.assert_allclose(result.z_scores, [2.0, 6.0, 0.0, -2.8, -3.2])
    assert result.flagged == [1, 4]
    assert result.n_shots == 100


def test_analyze_bias_chi_square_two_columns() -> None:
    # p = 0.6 and 0.8, pooled 0.7, shot-noise variance 0.21 / 100.
    result = analyze_bias(_columns_with_ones(100, [60, 80]))
    chi2 = (0.1**2 + 0.1**2) / (0.21 / 100)
    assert result.chi_square == pytest.approx(chi2)
    assert result.chi_square_dof == 1
    # For one degree of freedom the survival function is erfc(sqrt(x / 2)).
    assert result.chi_square_p == pytest.approx(math.erfc(math.sqrt(chi2 / 2)))


def test_analyze_bias_overall_mean_test() -> None:
    result = analyze_bias(_columns_with_ones(100, [60, 80]))
    assert result.mean_p_one == pytest.approx(0.7)
    z = 0.2 / math.sqrt(0.25 / 200)
    assert result.mean_z == pytest.approx(z)
    assert result.mean_p == pytest.approx(math.erfc(z / math.sqrt(2)))


def test_analyze_bias_pure_shot_noise_is_not_overdispersed() -> None:
    rng = np.random.default_rng(1234)
    bits = (rng.random((2000, 100)) < 0.5).astype(np.uint8)
    result = analyze_bias(bits)
    assert result.chi_square_dof == 99
    assert result.chi_square_p > 0.01
    assert result.mean_p > 0.01


def test_analyze_bias_detects_overdispersion() -> None:
    rng = np.random.default_rng(99)
    p = np.linspace(0.35, 0.65, 50)
    bits = (rng.random((2000, 50)) < p).astype(np.uint8)
    assert analyze_bias(bits).chi_square_p < 1e-6


def test_analyze_bias_keeps_every_qubit() -> None:
    bits = _columns_with_ones(100, [99, 50, 1])
    result = analyze_bias(bits)
    assert len(result.p_one) == 3
    assert len(result.z_scores) == 3
    assert result.flagged == [0, 2]


# --- Bitmap ----------------------------------------------------------------------------------


def test_bitmap_fills_rows_in_stream_order() -> None:
    bits = np.array([1, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1], dtype=np.uint8)
    np.testing.assert_array_equal(bitmap(bits, 3), [[1, 0, 0], [1, 1, 0], [0, 0, 1]])


def test_bitmap_flattens_2d_input_shot_major() -> None:
    bits = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    np.testing.assert_array_equal(bitmap(bits, 2), [[1, 0], [0, 1]])


def test_bitmap_needs_enough_bits() -> None:
    with pytest.raises(ValueError):
        bitmap(np.zeros(8, dtype=np.uint8), 3)


# --- Per-qubit entropy and estimator bias ----------------------------------------------------


def test_per_qubit_shannon_entropy_is_h_of_each_column() -> None:
    bits = np.array([[1, 0, 1], [0, 0, 1], [1, 0, 1], [0, 0, 0]], dtype=np.uint8)
    # Columns have P(1) = 0.5, 0.0 and 0.75.
    assert per_qubit_shannon_entropy(bits) == pytest.approx([1.0, 0.0, 0.8112781244591328])


def test_entropy_estimator_bias_formula() -> None:
    assert entropy_estimator_bias(2000) == pytest.approx(1 / (4000 * math.log(2)))
    with pytest.raises(ValueError):
        entropy_estimator_bias(0)


def test_entropy_estimator_bias_matches_simulated_fair_coins() -> None:
    n = 500
    bits = (np.random.default_rng(1).random((n, 4000)) < 0.5).astype(np.uint8)
    observed = 1.0 - per_qubit_shannon_entropy(bits).mean()
    assert observed == pytest.approx(entropy_estimator_bias(n), rel=0.1)


def test_entropy_shortfall_fair_coins_are_not_noticeable() -> None:
    bits = (np.random.default_rng(2).random((2000, 100)) < 0.5).astype(np.uint8)
    result = entropy_shortfall(bits)
    assert result.fair_chi_square_dof == 100
    assert result.shortfall == pytest.approx(1.0 - result.mean_entropy)
    assert result.estimator_bias == pytest.approx(entropy_estimator_bias(2000))
    assert not result.noticeable


def test_entropy_shortfall_biased_coins_are_noticeable() -> None:
    bits = (np.random.default_rng(3).random((2000, 100)) < 0.45).astype(np.uint8)
    result = entropy_shortfall(bits)
    assert result.noticeable
    assert result.shortfall > 5 * result.estimator_bias


@pytest.mark.parametrize(
    ("p_one", "direction"),
    [
        ([0.45] * 30, "toward_0"),
        ([0.55] * 30, "toward_1"),
        ([0.45, 0.55] * 15, "mixed"),
        ([0.5] * 4, "mixed"),
    ],
)
def test_bias_direction(p_one: list[float], direction: str) -> None:
    result = bias_direction(p_one)
    assert result.direction == direction
    assert result.n_below_half == sum(p < 0.5 for p in p_one)
    assert result.n_above_half == sum(p > 0.5 for p in p_one)


# --- Chance range for pure guessing ------------------------------------------------------------


def test_chance_range_for_twenty_guesses_by_hand() -> None:
    # P(6 <= X <= 14) for X ~ Binomial(20, 1/2) is 1 - 2 * 21700/2**20 = 0.95861...; the
    # next narrower range, 7 to 13, holds only 0.8847, so 6 to 14 is the narrowest >= 95%.
    result = chance_range(20)
    assert (result.low, result.high) == (6, 14)
    assert result.probability == pytest.approx(1 - 2 * 21700 / 2**20)
    assert result.coverage == 0.95


@pytest.mark.parametrize("n", [1, 2, 5, 20, 21, 100])
def test_chance_range_is_symmetric_and_narrowest(n: int) -> None:
    result = chance_range(n)
    assert result.low + result.high == n
    assert result.probability >= 0.95
    if result.high - result.low >= 2:
        narrower = sum(math.comb(n, k) for k in range(result.low + 1, result.high)) / 2**n
        assert narrower < 0.95


def test_chance_range_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        chance_range(0)
    with pytest.raises(ValueError):
        chance_range(20, coverage=1.5)
