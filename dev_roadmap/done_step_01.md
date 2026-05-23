# Step 01 — Project skeleton & tooling

## Goal

Make `pip install -e .` succeed and `pytest` run a zero-test suite cleanly. Establish the package layout, entry point, and dev tooling that every subsequent step assumes.

## Files created

- `pyproject.toml`
- `.gitignore`
- `bal_sbx/__init__.py` (empty, with a `__version__` placeholder)
- `bal_sbx/__main__.py` (placeholder that prints a "not yet wired" message and exits 0 — replaced in step 09)
- `tests/__init__.py`
- `tests/conftest.py` (empty for now; fakes arrive in step 04)
- `tests/unit/__init__.py`

## Public surface introduced

None yet. The package is importable but exposes nothing.

## Acceptance criteria

### Code
- `pyproject.toml` uses `setuptools` + `setuptools-scm` (mirror `bal`'s setup), Python `>=3.11`, project name `bal-sbx`, package name `bal_sbx`.
- Console entry point declared: `bal-sbx = "bal_sbx.cli.main:main"`. The target does not exist yet — that is acceptable for this step, but the entry point line must be present so step 09 only needs to add the function, not the wiring.
- Optional dev extras: `dev = ["pytest>=8", "ruff>=0.5"]`. No runtime dependencies — `bal-sbx` is stdlib-only by design.
- `ruff` config (in `pyproject.toml`): line length 120, target Python 3.11.
- `pytest` config (in `pyproject.toml`): `testpaths = ["tests"]`, `addopts = "-ra --strict-markers"`.

### Tests
- `pytest` exits 0 with "no tests ran" — proves the harness is discoverable.

## Notes / gotchas

- Do **not** install `bal-sbx` into the project's interpreter from CI yet; the entry point references a missing function and any `bal-sbx --help` invocation will fail until step 09.
- Keep `bal_sbx/__init__.py` empty. Public exports are added incrementally; an early `from .api import SandboxManager` would create import-time failures across later steps.
- The `LICENSE` file already exists at repo root (MIT). Do not modify it.
