import random

import numpy as np
import pytest

from pipeline.attacker import (
    MT_STATE_WORDS,
    BiasAttacker,
    MersenneTwisterAttacker,
    PreviousShotAttacker,
    cross_checks,
    running_accuracy,
    stream_as_shots,
    untemper,
)
from pipeline.classical import generate_words, urandom_words, words_to_bits


def _temper(y: int) -> int:
    """MT19937 tempering, written out independently of pipeline.attacker."""
    y ^= y >> 11
    y ^= (y << 7) & 0x9D2C5680
    y ^= (y << 15) & 0xEFC60000
    y ^= y >> 18
    return y & 0xFFFFFFFF


# --- Running accuracy ------------------------------------------------------------------------


def test_running_accuracy_short_series_keeps_every_point() -> None:
    index, acc = running_accuracy(np.array([True, False, True, True]))
    np.testing.assert_array_equal(index, [1, 2, 3, 4])
    np.testing.assert_allclose(acc, [1.0, 0.5, 2 / 3, 0.75])


def test_running_accuracy_downsamples_to_about_500_points() -> None:
    correct = np.zeros(100_000, dtype=bool)
    correct[::4] = True
    index, acc = running_accuracy(correct)
    assert 450 <= len(index) <= 500
    assert index[0] == 1
    assert index[-1] == 100_000
    assert np.all(np.diff(index) > 0)
    assert acc[0] == 1.0
    assert acc[-1] == pytest.approx(0.25)


def test_running_accuracy_rejects_empty() -> None:
    with pytest.raises(ValueError):
        running_accuracy(np.array([], dtype=bool))


# --- Untempering -----------------------------------------------------------------------------


def test_untemper_inverts_tempering() -> None:
    rng = np.random.default_rng(7)
    samples = [0, 1, 0xFFFFFFFF, 0x80000000, *rng.integers(0, 2**32, 1000).tolist()]
    for y in samples:
        assert untemper(_temper(int(y))) == y


def test_untemper_matches_cpython_state() -> None:
    # The untempered first 624 outputs after seeding are exactly CPython's internal state.
    rng = random.Random(2024)
    outputs = [rng.getrandbits(32) for _ in range(MT_STATE_WORDS)]
    state_after = rng.getstate()[1]
    assert [untemper(w) for w in outputs] == list(state_after[:MT_STATE_WORDS])


# --- Mersenne Twister attacker ---------------------------------------------------------------


def test_mt_attacker_predicts_10000_held_out_words_exactly() -> None:
    words = generate_words(MT_STATE_WORDS + 10_000)
    result = MersenneTwisterAttacker().attack(words)
    assert result.accuracy == 1.0
    assert result.n_predicted == 10_000 * 32
    assert result.n_training_bits == MT_STATE_WORDS * 32
    assert result.min_entropy == 0.0
    assert np.all(result.running_accuracy == 1.0)
    assert len(result.predictions) == result.n_predicted


def test_mt_attacker_works_from_any_offset() -> None:
    # The attacker is not told where the generator's internal block boundary is.
    words = generate_words(5_000)[1_234:]
    assert MersenneTwisterAttacker().attack(words).accuracy == 1.0


def test_mt_attacker_on_non_mt_words_is_a_coin_flip() -> None:
    words = np.random.default_rng(5).integers(0, 2**32, MT_STATE_WORDS + 5_000, dtype=np.uint32)
    result = MersenneTwisterAttacker().attack(words)
    assert result.accuracy == pytest.approx(0.5, abs=0.01)
    assert result.min_entropy > 0.97


def test_mt_attacker_needs_held_out_words() -> None:
    with pytest.raises(ValueError):
        MersenneTwisterAttacker().attack(generate_words(MT_STATE_WORDS))


# --- Bias attacker ---------------------------------------------------------------------------


def test_bias_attacker_on_bernoulli_045_converges_to_055() -> None:
    rng = np.random.default_rng(42)
    bits = (rng.random((2000, 100)) < 0.45).astype(np.uint8)
    result = BiasAttacker().attack(bits)
    assert result.accuracy == pytest.approx(0.55, abs=0.005)
    assert result.n_predicted == 1000 * 100
    assert result.n_training_bits == 1000 * 100
    assert result.min_entropy == pytest.approx(0.8625, abs=0.015)
    assert result.per_qubit_accuracy is not None
    assert result.per_qubit_accuracy.shape == (100,)
    assert result.running_accuracy[-1] == pytest.approx(result.accuracy)


def test_bias_attacker_predicts_each_qubits_majority() -> None:
    bits = np.zeros((10, 3), dtype=np.uint8)
    bits[:, 0] = 1  # always 1
    bits[:, 2] = [1, 1, 1, 0, 1, 0, 0, 0, 1, 0]  # training majority 1; held-out 1 of 5
    result = BiasAttacker().attack(bits)
    assert result.per_qubit_accuracy is not None
    np.testing.assert_allclose(result.per_qubit_accuracy, [1.0, 1.0, 0.2])
    np.testing.assert_array_equal(result.predictions[:3], [1, 0, 1])


def test_bias_attacker_learns_only_from_training_half() -> None:
    bits = np.zeros((100, 4), dtype=np.uint8)
    bits[:50] = 1  # training half all ones, held-out half all zeros
    result = BiasAttacker().attack(bits)
    assert result.accuracy == 0.0
    # Always wrong means flipping every guess is always right: fully predictable.
    assert result.min_entropy == 0.0


def test_bias_attacker_reports_wilson_interval() -> None:
    rng = np.random.default_rng(3)
    bits = (rng.random((400, 50)) < 0.4).astype(np.uint8)
    result = BiasAttacker().attack(bits)
    assert result.ci_low < result.accuracy < result.ci_high
    # Above 0.5 the upper bound is the more predictable one.
    assert result.min_entropy_conservative == pytest.approx(-np.log2(result.ci_high))


def test_conservative_min_entropy_below_half_uses_lower_bound() -> None:
    # Training half all ones; held-out half 30% ones, so the attacker scores about 0.3.
    rng = np.random.default_rng(8)
    bits = np.ones((800, 50), dtype=np.uint8)
    bits[400:] = (rng.random((400, 50)) < 0.3).astype(np.uint8)
    result = BiasAttacker().attack(bits)
    assert result.accuracy < 0.5
    # max(a, 1 - a) is largest at ci_low here, so that bound is the conservative one.
    assert result.min_entropy_conservative == pytest.approx(-np.log2(1 - result.ci_low))
    assert result.min_entropy_conservative < result.min_entropy


def test_cross_checks_score_about_half() -> None:
    # Biased quantum-like bits and a real MT stream: each attacker on the wrong stream.
    rng = np.random.default_rng(11)
    q_bits = (rng.random((2000, 100)) < 0.45).astype(np.uint8)
    words = generate_words(6250)
    checks = cross_checks(q_bits, words)
    assert checks.mt_on_quantum.attacker == MersenneTwisterAttacker.name
    assert checks.bias_on_classical.attacker == BiasAttacker.name
    # Quantum bits pack into 6250 words, 624 observed, the rest predicted.
    assert checks.mt_on_quantum.n_predicted == (6250 - MT_STATE_WORDS) * 32
    # Classical bits are reshaped like the quantum array and split in half by shots.
    assert checks.bias_on_classical.n_predicted == 1000 * 100
    for result in (checks.mt_on_quantum, checks.bias_on_classical):
        assert result.accuracy == pytest.approx(0.5, abs=0.01)


def test_bias_attacker_needs_two_shots() -> None:
    with pytest.raises(ValueError):
        BiasAttacker().attack(np.zeros((1, 5), dtype=np.uint8))


# --- Previous-shot attacker ------------------------------------------------------------------


def test_previous_shot_attacker_predicts_alternating_bits() -> None:
    column = np.arange(100) % 2
    bits = np.stack([column, 1 - column, np.ones(100, dtype=np.int64)], axis=1).astype(np.uint8)
    result = PreviousShotAttacker().attack(bits)
    assert result.accuracy == 1.0
    assert result.n_predicted == 50 * 3
    assert result.n_training_bits == 50 * 3
    assert result.per_qubit_accuracy is not None
    assert result.per_qubit_accuracy.tolist() == [1.0, 1.0, 1.0]


def test_previous_shot_attacker_uses_last_training_shot_for_first_prediction() -> None:
    # Training shots repeat, so the attacker predicts "same as before". The first held-out
    # prediction must therefore equal the last training shot.
    bits = np.array([[0], [0], [1], [1]], dtype=np.uint8)
    result = PreviousShotAttacker().attack(bits)
    assert result.predictions.tolist() == [0, 1]


def test_previous_shot_attacker_scores_about_half_on_independent_biased_bits() -> None:
    bits = (np.random.default_rng(4).random((2000, 100)) < 0.45).astype(np.uint8)
    result = PreviousShotAttacker().attack(bits)
    assert abs(result.accuracy - 0.5) < 0.01


def test_previous_shot_attacker_needs_two_training_shots() -> None:
    with pytest.raises(ValueError):
        PreviousShotAttacker().attack(np.zeros((3, 2), dtype=np.uint8))


def test_stream_as_shots_takes_the_prefix_in_order() -> None:
    assert stream_as_shots([1, 0, 1, 1, 0, 0, 1], (2, 3)).tolist() == [[1, 0, 1], [1, 0, 0]]
    with pytest.raises(ValueError):
        stream_as_shots([1, 0], (2, 3))


def test_consistent_with_chance() -> None:
    perfect = BiasAttacker().attack(np.ones((100, 4), dtype=np.uint8))
    assert not perfect.consistent_with_chance
    words = urandom_words(4000)
    fair = BiasAttacker().attack(stream_as_shots(words_to_bits(words), (1280, 100)))
    assert fair.ci_low < fair.ci_high
    assert fair.consistent_with_chance is (fair.ci_low <= 0.5 <= fair.ci_high)
