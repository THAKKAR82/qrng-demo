"""The two attackers from SPEC.md, Section 3.1. Both are scored only on held-out data.

- ``MersenneTwisterAttacker`` sees 624 consecutive 32-bit outputs of Python's ``random``,
  undoes the tempering to recover the generator's full internal state, and predicts every
  later output.
- ``BiasAttacker`` sees the first half of the quantum shots, learns each qubit's more
  common value, and guesses that value for the same qubit on every held-out shot.

Neither attacker ever sees the classical seed; it only sees outputs.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from pipeline.analysis import min_entropy_from_accuracy, wilson_interval
from pipeline.classical import WORD_BITS, words_to_bits

MT_STATE_WORDS = 624  # MT19937 keeps 624 words of 32 bits as its whole state
RUNNING_POINTS = 500
_MASK32 = 0xFFFFFFFF


@dataclass(frozen=True)
class AttackResult:
    attacker: str
    accuracy: float  # P_guess: fraction of held-out bits predicted correctly
    n_predicted: int  # held-out bits predicted
    n_correct: int
    n_training_bits: int  # bits the attacker observed before predicting
    ci_low: float  # 95% Wilson interval for accuracy
    ci_high: float
    min_entropy: float  # H∞ at the point estimate, capped at 1 bit
    min_entropy_conservative: float  # H∞ at ci_high
    # Accuracy over the first running_index[i] predicted bits, downsampled.
    running_index: npt.NDArray[np.int64]
    running_accuracy: npt.NDArray[np.float64]
    # The attacker's guess for each held-out bit, in stream order.
    predictions: npt.NDArray[np.uint8]
    per_qubit_accuracy: npt.NDArray[np.float64] | None = None


def running_accuracy(
    correct: npt.ArrayLike, max_points: int = RUNNING_POINTS
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64]]:
    """Cumulative accuracy after each prediction, sampled at no more than ``max_points``
    evenly spaced positions. The first and last predictions are always included."""
    hits = np.asarray(correct, dtype=bool).reshape(-1)
    if hits.size == 0:
        raise ValueError("no predictions to score")
    n = hits.size
    if n <= max_points:
        index = np.arange(1, n + 1, dtype=np.int64)
    else:
        index = np.unique(np.rint(np.linspace(1, n, max_points)).astype(np.int64))
    cumulative = np.cumsum(hits, dtype=np.int64)
    return index, cumulative[index - 1] / index


def _score(
    attacker: str,
    predictions: npt.NDArray[np.uint8],
    actual: npt.NDArray[np.uint8],
    n_training_bits: int,
    per_qubit_accuracy: npt.NDArray[np.float64] | None = None,
) -> AttackResult:
    correct = predictions == actual
    n_predicted = int(correct.size)
    n_correct = int(correct.sum())
    accuracy = n_correct / n_predicted
    ci_low, ci_high = wilson_interval(n_correct, n_predicted)
    index, running = running_accuracy(correct)
    return AttackResult(
        attacker=attacker,
        accuracy=accuracy,
        n_predicted=n_predicted,
        n_correct=n_correct,
        n_training_bits=n_training_bits,
        ci_low=ci_low,
        ci_high=ci_high,
        min_entropy=min_entropy_from_accuracy(accuracy),
        min_entropy_conservative=min_entropy_from_accuracy(ci_high),
        running_index=index,
        running_accuracy=running,
        predictions=predictions,
        per_qubit_accuracy=per_qubit_accuracy,
    )


# --- Mersenne Twister state recovery ---------------------------------------------------------
#
# Each MT19937 output is one state word y passed through "tempering":
#
#     y ^= y >> 11
#     y ^= (y << 7)  & 0x9D2C5680
#     y ^= (y << 15) & 0xEFC60000
#     y ^= y >> 18
#
# Every step is invertible, so we undo them in reverse order.


def _undo_xor_right_shift(value: int, shift: int) -> int:
    """Invert ``y ^= y >> shift``.

    The top ``shift`` bits of the output equal the top bits of ``y``, because nothing was
    XORed into them. With those known, the next ``shift`` bits can be recovered, and so on
    down the word. Each pass fixes ``shift`` more bits, so ceil(32 / shift) passes suffice.
    """
    result = value
    for _ in range(-(-WORD_BITS // shift)):
        result = value ^ (result >> shift)
    return result & _MASK32


def _undo_xor_left_shift_and(value: int, shift: int, mask: int) -> int:
    """Invert ``y ^= (y << shift) & mask``.

    This is the mirror image: the bottom ``shift`` bits of the output equal those of ``y``,
    and each pass recovers the next ``shift`` bits upwards.
    """
    result = value
    for _ in range(-(-WORD_BITS // shift)):
        result = value ^ ((result << shift) & mask)
    return result & _MASK32


def untemper(output: int) -> int:
    """Recover the MT19937 state word that produced one 32-bit output."""
    y = _undo_xor_right_shift(output, 18)
    y = _undo_xor_left_shift_and(y, 15, 0xEFC60000)
    y = _undo_xor_left_shift_and(y, 7, 0x9D2C5680)
    return _undo_xor_right_shift(y, 11)


class MersenneTwisterAttacker:
    """Recovers the MT19937 state from 624 consecutive outputs and predicts the rest."""

    name = "Mersenne Twister state recovery"

    @staticmethod
    def clone_generator(observed: npt.ArrayLike) -> random.Random:
        """A ``random.Random`` in the same state as the generator right after it produced
        ``observed`` (exactly 624 consecutive ``getrandbits(32)`` outputs)."""
        words = [int(w) for w in np.asarray(observed, dtype=np.uint32).reshape(-1)]
        if len(words) != MT_STATE_WORDS:
            raise ValueError(f"need exactly {MT_STATE_WORDS} words, got {len(words)}")
        state = [untemper(w) for w in words]
        # CPython stores the 624 state words followed by an index. Index 624 means "all
        # words used", so the next call regenerates (twists) the state before outputting.
        # The twist computes each new word from words i, i+1 and i+397 of the window, so
        # any 624 consecutive outputs work, whether or not they start on a block boundary.
        clone = random.Random()
        clone.setstate((random.Random.VERSION, (*state, MT_STATE_WORDS), None))
        return clone

    def attack(self, words: npt.ArrayLike) -> AttackResult:
        stream = np.asarray(words, dtype=np.uint32).reshape(-1)
        if stream.size <= MT_STATE_WORDS:
            raise ValueError(f"need more than {MT_STATE_WORDS} words to hold any out")
        clone = self.clone_generator(stream[:MT_STATE_WORDS])
        held_out = stream[MT_STATE_WORDS:]
        predicted_words = np.fromiter(
            (clone.getrandbits(WORD_BITS) for _ in range(held_out.size)),
            dtype=np.uint32,
            count=held_out.size,
        )
        return _score(
            self.name,
            predictions=words_to_bits(predicted_words),
            actual=words_to_bits(held_out),
            n_training_bits=MT_STATE_WORDS * WORD_BITS,
        )


class BiasAttacker:
    """Learns each qubit's majority value on the training shots and always guesses it."""

    name = "Per-qubit bias (majority vote)"

    def __init__(self, train_fraction: float = 0.5) -> None:
        if not 0.0 < train_fraction < 1.0:
            raise ValueError("train_fraction must be between 0 and 1")
        self.train_fraction = train_fraction

    def split(self, n_shots: int) -> int:
        """Number of training shots; the rest are held out."""
        return int(n_shots * self.train_fraction)

    def attack(self, bits_2d: npt.ArrayLike) -> AttackResult:
        bits = np.asarray(bits_2d, dtype=np.uint8)
        if bits.ndim != 2:
            raise ValueError(f"expected a (shots, qubits) array, got shape {bits.shape}")
        n_train = self.split(bits.shape[0])
        if n_train == 0 or n_train == bits.shape[0]:
            raise ValueError("need at least one training shot and one held-out shot")
        train, held_out = bits[:n_train], bits[n_train:]
        # Majority value per qubit. A tie guesses 0.
        guess = (train.mean(axis=0) > 0.5).astype(np.uint8)
        predictions = np.broadcast_to(guess, held_out.shape)
        per_qubit = (predictions == held_out).mean(axis=0, dtype=np.float64)
        return _score(
            self.name,
            # Shot-major order, matching how the stream is flattened (SPEC.md, Section 5.2).
            predictions=predictions.reshape(-1).copy(),
            actual=held_out.reshape(-1),
            n_training_bits=int(train.size),
            per_qubit_accuracy=per_qubit,
        )
