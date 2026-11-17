## Checks

Run all of these before committing; they must pass. While the repo is private, run them locally instead of relying on GitHub Actions CI.

Start from the same environment CI uses. `uv sync` removes packages from other groups (such as FMPy from `bench`), which would otherwise hide missing-import errors:

```sh
uv sync --locked --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run mypy
uv run pyright
```

CI also type-checks on Windows and macOS, where some standard-library modules (like `resource`) don't exist, so check those platforms too:

```sh
uv run mypy --platform win32 && uv run mypy --platform darwin
uv run pyright --pythonplatform Windows && uv run pyright --pythonplatform Darwin
```

Tests marked `slow` (million-variable memory checks, about a minute) are skipped by default; run them when touching the reader, the grammars or the variable stream:

```sh
uv run pytest -m slow
```

Benchmarks against FMPy (Linux/macOS; regenerates `benchmarks/RESULTS.md`):

```sh
uv run --group bench python benchmarks/bench.py --output benchmarks/RESULTS.md
```

Python 3.10 is the oldest supported version, so also run the tests on it:

```sh
UV_PROJECT_ENVIRONMENT=<scratch dir>/venv310 uv run --python 3.10 --group dev pytest
```

## Agent skills

### Issue tracker

Issues live in GitHub Issues for this repo, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
