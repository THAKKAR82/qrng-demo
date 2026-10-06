import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import classical, runs


def test_words_needed_rounds_up() -> None:
    assert classical.words_needed(1) == 1
    assert classical.words_needed(32) == 1
    assert classical.words_needed(33) == 2
    with pytest.raises(ValueError):
        classical.words_needed(0)


def test_words_unpack_msb_first() -> None:
    # 0x80000001: top bit and bottom bit set. 0x00000002: second-lowest bit set.
    bits = classical.words_to_bits(np.array([0x80000001, 0x00000002], dtype=np.uint32))
    assert bits.dtype == np.uint8
    assert bits.shape == (64,)
    assert bits[:32].tolist() == [1] + [0] * 30 + [1]
    assert bits[32:].tolist() == [0] * 30 + [1, 0]


def test_bits_pack_msb_first() -> None:
    bits = [1] + [0] * 30 + [1] + [0] * 30 + [1, 0]
    words = classical.bits_to_words(np.array(bits, dtype=np.uint8))
    assert words.dtype == np.uint32
    assert words.tolist() == [0x80000001, 0x00000002]


def test_bits_to_words_drops_a_partial_last_word() -> None:
    bits = np.ones(70, dtype=np.uint8)
    assert classical.bits_to_words(bits).tolist() == [0xFFFFFFFF, 0xFFFFFFFF]


def test_words_to_bits_matches_spec_formula() -> None:
    words = classical.generate_words(4)
    expected = [(int(w) >> (31 - i)) & 1 for w in words for i in range(32)]
    assert classical.words_to_bits(words).tolist() == expected


def test_generate_words_type_and_length() -> None:
    words = classical.generate_words(700)
    assert words.dtype == np.uint32
    assert words.shape == (700,)
    # Two fresh generators should not agree (each is seeded from os.urandom).
    assert not np.array_equal(words, classical.generate_words(700))


def test_write_classical_files_and_metadata(tmp_path: Path) -> None:
    meta = classical.write_classical(tmp_path, 100, run_id="r1", synthetic=False)
    with np.load(tmp_path / runs.CLASSICAL_NPZ) as data:
        assert list(data.keys()) == ["words"]
        assert data["words"].dtype == np.uint32
        assert data["words"].shape == (4,)
    on_disk = json.loads((tmp_path / runs.CLASSICAL_JSON).read_text())
    assert on_disk == meta
    assert meta["seed_stored"] is False
    assert meta["seed_discarded"] is True
    assert meta["seed_source"] == "os.urandom"
    assert meta["bit_order"] == "msb_first"
    assert meta["matched_bits"] == 100
    assert meta["n_bits"] == 128
    assert "seed" not in meta


def test_write_classical_refuses_to_overwrite(tmp_path: Path) -> None:
    classical.write_classical(tmp_path, 64, run_id="r1", synthetic=False)
    with pytest.raises(FileExistsError):
        classical.write_classical(tmp_path, 64, run_id="r1", synthetic=False)


def test_collect_for_folder_matches_quantum_bits(tmp_path: Path) -> None:
    np.savez_compressed(tmp_path / runs.QUANTUM_NPZ, bits=np.zeros((10, 7), dtype=np.uint8))
    runs.write_json(tmp_path / runs.QUANTUM_JSON, {"synthetic": False})
    meta = classical.collect_for_folder(tmp_path)
    assert meta["matched_bits"] == 70
    assert meta["n_words"] == 3
    assert meta["synthetic"] is False
    assert meta["run_id"] == tmp_path.name


def test_collect_for_folder_needs_bits_without_quantum(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        classical.collect_for_folder(tmp_path)
    meta = classical.collect_for_folder(tmp_path, n_bits=64)
    assert meta["n_words"] == 2
    assert meta["synthetic"] is True


def test_collect_for_folder_rejects_mismatched_bits(tmp_path: Path) -> None:
    np.savez_compressed(tmp_path / runs.QUANTUM_NPZ, bits=np.zeros((2, 2), dtype=np.uint8))
    with pytest.raises(ValueError):
        classical.collect_for_folder(tmp_path, n_bits=5)
