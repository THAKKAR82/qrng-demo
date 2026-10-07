"""The UI's display-only statistics (SPEC.md, Section 7) agree with pipeline.analysis on the
same bits, and its pool reads never repeat or wrap. Runs the TypeScript under Node, which
strips the types itself; no browser and no network."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pipeline import export
from pipeline.analysis import binary_entropy, shannon_entropy_per_bit
from pipeline.paths import SAMPLE_DIR, UI_DIR

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required for the UI checks")


def _node(*args: str) -> subprocess.CompletedProcess[str]:
    assert NODE is not None
    return subprocess.run(
        [NODE, *args], cwd=UI_DIR, capture_output=True, text=True, check=False, timeout=120
    )


@pytest.fixture(scope="module")
def sample_demo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo") / "demo.json"
    export.write_demo(SAMPLE_DIR / "synthetic-v1", out, is_sample=True)
    return out


@pytest.mark.parametrize("which", ["sample", "committed"])
def test_ts_stats_match_python(which: str, sample_demo: Path) -> None:
    path = sample_demo if which == "sample" else export.DEMO_JSON
    demo = json.loads(path.read_text(encoding="utf-8"))
    result = _node("scripts/stats-check.ts", str(path))
    assert result.returncode == 0, result.stderr
    report: dict[str, Any] = json.loads(result.stdout)

    for source in ("classical", "quantum"):
        pool = demo[source]["pool"]
        bits = export.unpack_bits(pool["bits"], pool["n_bits"])
        predictions = export.unpack_bits(pool["predictions"], pool["n_bits"])
        ts = report[source]
        # Same decoding of the packed pool.
        assert ts["bits"] == "".join(map(str, bits.tolist()))
        assert ts["predictions"] == "".join(map(str, predictions.tolist()))
        assert ts["prefixes"][-1]["n"] == pool["n_bits"]
        for row in ts["prefixes"]:
            n = row["n"]
            shown = bits[:n]
            assert row["ones"] == int(shown.sum())
            assert row["fraction_ones"] == pytest.approx(float(shown.mean()), abs=1e-12)
            assert row["entropy"] == pytest.approx(shannon_entropy_per_bit(shown), abs=1e-12)
            assert row["matches"] == int(np.sum(shown == predictions[:n]))


def test_ts_binary_entropy_edges_match_python(tmp_path: Path) -> None:
    script = tmp_path / "edges.ts"
    lib = (UI_DIR / "src" / "lib" / "stats.ts").as_uri()
    ps = [0, 1, 0.5, 0.25, 1e-9, 0.999999, -1, 2]
    script.write_text(
        f"import {{ binaryEntropy }} from '{lib}'\n"
        f"console.log(JSON.stringify({json.dumps(ps)}.map(binaryEntropy)))\n",
        encoding="utf-8",
    )
    result = _node(str(script))
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    for p, value in zip(ps, values, strict=True):
        assert value == pytest.approx(binary_entropy(p), abs=1e-15)


def test_pool_reads_never_wrap() -> None:
    result = _node("--test", "scripts/pool.test.ts")
    assert result.returncode == 0, result.stdout + result.stderr
