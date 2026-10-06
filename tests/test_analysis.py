import math

import numpy as np
import pytest

from pipeline.analysis import (
    analyze_bias,
    bias_per_qubit,
    bitmap,
    min_entropy_from_accuracy,
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
    ],
)
def test_min_entropy_from_accuracy(p_guess: float, expected: float) -> None:
    assert min_entropy_from_accuracy(p_guess) == pytest.approx(expected)


def test_min_entropy_of_perfect_prediction_is_positive_zero() -> None:
    assert math.copysign(1.0, min_entropy_from_accuracy(1.0)) == 1.0


@pytest.mark.parametrize("p_guess", [0.0, 0.3, 0.4999])
def test_min_entropy_below_coin_flip_is_capped_at_one_bit(p_guess: float) -> None:
    # A binary guesser can never truly do worse than 0.5; below it is sampling noise.
    assert min_entropy_from_accuracy(p_guess) == 1.0


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
