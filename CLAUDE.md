## Checks

Run all of these before committing; they must pass. While the repo is private, run them locally instead of relying on GitHub Actions CI.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run mypy
uv run pyright
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
