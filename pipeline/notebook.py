"""Execute ``notebooks/qrng_demo.ipynb`` into ``data/scratch/`` (SPEC.md, Section 8).

The notebook chooses its data folder exactly as ``export`` does. These environment
variables override that choice, the same way ``export --run`` and ``--sample`` do; the
executed kernel inherits them.
"""

from __future__ import annotations

import os
from pathlib import Path

from pipeline.paths import NOTEBOOKS_DIR, REPO_ROOT, SCRATCH_DATA_DIR

NOTEBOOK = NOTEBOOKS_DIR / "qrng_demo.ipynb"
RUN_ENV = "QRNG_NOTEBOOK_RUN"
SAMPLE_ENV = "QRNG_NOTEBOOK_SAMPLE"
TIMEOUT_SECONDS = 600


def source_from_env() -> tuple[str | None, str | None]:
    """``(run, sample)`` for ``export.resolve_source``; both ``None`` means "latest"."""
    return os.environ.get(RUN_ENV) or None, os.environ.get(SAMPLE_ENV) or None


def execute(
    run: str | None = None,
    sample: str | None = None,
    *,
    notebook: Path = NOTEBOOK,
    out_dir: Path = SCRATCH_DATA_DIR,
) -> Path:
    """Run every cell top to bottom and write the executed copy to ``out_dir``.

    Raises ``nbclient.exceptions.CellExecutionError`` if any cell fails.
    """
    import nbformat
    from nbclient import NotebookClient

    nb = nbformat.read(notebook, as_version=4)
    env = {k: v for k, v in os.environ.items() if k not in (RUN_ENV, SAMPLE_ENV)}
    if run is not None:
        env[RUN_ENV] = run
    if sample is not None:
        env[SAMPLE_ENV] = sample
    client = NotebookClient(
        nb,
        timeout=TIMEOUT_SECONDS,
        kernel_name="python3",
        # The kernel starts in the repo root so ``import pipeline`` works even when the
        # editable install's .pth file is skipped (Python 3.13 ignores .pth files that carry
        # the macOS "hidden" flag). The pipeline itself resolves paths from paths.py.
        resources={"metadata": {"path": str(REPO_ROOT)}},
    )
    client.execute(env=env)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / notebook.name
    nbformat.write(nb, target)
    return target
