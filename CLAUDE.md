# Working rules for Claude in this repo

SPEC.md is the source of truth. These rules apply in every session.

## Hard rules

1. **Never run real quantum collection or the refresh task.** Never run code that submits jobs to IBM Quantum or creates a `QiskitRuntimeService` against real hardware. That includes `python -m pipeline.tasks collect-quantum` and `refresh`, ad-hoc scripts, notebook cells, and `python -c`. The human runs real collection. Work with mocks, committed runs in `data/runs/`, synthetic data in `data/sample/`, and `collect-quantum --dry-run`, which uses a local fake backend and no account.
2. **Never read, list, print, or copy anything from `~/.qiskit`** or any other credentials file (`.env*`, `qiskit-ibm.json`, keychains). This includes doing it indirectly through Python, Node, or shell commands, or calling `active_account()`, `saved_accounts()`, `instances()`, or `active_instance()`.
3. **Never `git push`**, in any form. At the end of each task, commit with a clear message; the human reviews and pushes.
4. **Read SPEC.md before starting any task.** Before committing, run lint, type checks, and tests (see below) and make sure they pass.
5. **Prefer current official documentation over memory** for qiskit, qiskit-ibm-runtime, Vite, and React APIs. When the docs are unclear, check the installed version's source in `.venv`.
6. **Both machines run macOS.** Use `pathlib` for every path and resolve paths from `pipeline/paths.py`, never from the current directory.

Also follow the honesty rules in SPEC.md, Section 4. In short: synthetic data is always labelled; never claim quantum bits have higher Shannon entropy; every on-screen number comes from `results.json`; never debias or mitigate the reported bits.

## Checks before every commit

```sh
source .venv/bin/activate
ruff check . && ruff format --check .
mypy
pytest
(cd ui && npm run lint && npm run typecheck)
pre-commit run --all-files
```

## Notes

- The deny rules in `.claude/settings.json` back up rules 1–3, but they match command text only, so they are not a complete boundary. The rules above still apply when no deny rule fires.
- The deny rules block any shell command that mentions `.qiskit` or `QiskitRuntimeService`. Grep for the class with a pattern such as `RuntimeService` instead.
- Don't run `npm audit fix --force`. It downgrades `vite-plugin-singlefile`.
