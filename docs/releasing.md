# Releasing

Releases are published to PyPI by `.github/workflows/release.yml` when a `v*` tag is pushed. The workflow uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no PyPI API token is stored anywhere.

## One-time setup

1. **Check the name is free:** `pip index versions mdxml` should report that no matching distribution was found. If the name is taken, change `[project].name` in `pyproject.toml` first.
2. **Create a pending trusted publisher on PyPI** (Account settings → Publishing → Add a new pending publisher), with:
   - PyPI project name: `mdxml`
   - Owner: `hyumo`
   - Repository name: `mdxml`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
3. **Create the `pypi` environment on GitHub** (repository Settings → Environments → New environment → `pypi`). Adding yourself as a required reviewer makes every publish wait for your approval.

## Each release

1. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` (today's date), and add a fresh, empty `## [Unreleased]` above it.
2. Set `version = "X.Y.Z"` in `pyproject.toml`.
3. Check that the release check passes: `python scripts/check_release.py vX.Y.Z`.
4. Commit, then tag and push:

   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

The workflow then:

1. checks that the tag, `pyproject.toml` and `CHANGELOG.md` agree, and runs ruff, the tests, mypy and pyright;
2. builds the sdist and wheel, and checks the wheel has no XSD files, no runtime dependencies and a `py.typed` marker;
3. publishes both to PyPI from the `pypi` environment;
4. creates the GitHub release for the tag, with the changelog section as its notes and the same wheel and sdist attached (tags like `v1.0.0rc1` become pre-releases).

A tag without a matching version or a dated changelog section with at least one entry fails in the first step, so nothing is published.
