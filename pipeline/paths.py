"""Repository paths. Everything is resolved relative to the repo root, never the CWD."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"
SAMPLE_DIR = DATA_DIR / "sample"
SCRATCH_DATA_DIR = DATA_DIR / "scratch"
UI_DIR = REPO_ROOT / "ui"
UI_DATA_DIR = UI_DIR / "src" / "data"
DEMO_DIR = REPO_ROOT / "demo"
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"
