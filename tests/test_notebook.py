"""The notebook must run top to bottom (SPEC.md, Section 8). It is executed against the
synthetic sample, which must show the SYNTHETIC banner."""

from pathlib import Path

import nbformat

from pipeline import notebook
from pipeline.plotstyle import SYNTHETIC_LABEL
from pipeline.sample import SAMPLE_NAME


def test_committed_notebook_has_no_outputs() -> None:
    nb = nbformat.read(notebook.NOTEBOOK, as_version=4)
    for cell in nb.cells:
        if cell.cell_type == "code":
            assert cell.outputs == []
            assert cell.execution_count is None


def test_notebook_runs_on_the_sample_with_a_synthetic_banner(tmp_path: Path) -> None:
    target = notebook.execute(sample=SAMPLE_NAME, out_dir=tmp_path)
    nb = nbformat.read(target, as_version=4)
    outputs = [o for cell in nb.cells if cell.cell_type == "code" for o in cell.outputs]
    assert not [o for o in outputs if o.output_type == "error"]
    banners = [o for o in outputs if SYNTHETIC_LABEL in o.get("data", {}).get("text/html", "")]
    assert banners, "synthetic data must show the banner"
    assert any("image/png" in o.get("data", {}) for o in outputs)
