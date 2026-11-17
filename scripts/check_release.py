"""Check that a release tag is ready to publish, or print its release notes.

Usage: python scripts/check_release.py v1.2.3
       python scripts/check_release.py --notes v1.2.3

- The tag is ``v`` followed by the version in ``pyproject.toml``.
- ``CHANGELOG.md`` has a dated section for that version, ``## [1.2.3] - YYYY-MM-DD``,
  with at least one entry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PROJECT_VERSION = re.compile(r'^\[project\]$.*?^version\s*=\s*"([^"]+)"', re.MULTILINE | re.DOTALL)
_TAG = re.compile(r"v(\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)")


def project_version(pyproject: str) -> str | None:
    """Return the ``[project]`` version declared in ``pyproject.toml``'s text."""
    match = _PROJECT_VERSION.search(pyproject)
    return match.group(1) if match else None


def changelog_section(changelog: str, version: str) -> str | None:
    """Return the body of the changelog's ``## [version] - YYYY-MM-DD`` section, or ``None``."""
    heading = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$", re.MULTILINE)
    match = heading.search(changelog)
    if match is None:
        return None
    rest = changelog[match.end() :]
    following = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: following.start()] if following else rest


def release_notes(changelog: str, tag: str) -> str:
    """Return the GitHub release notes for ``tag``: its changelog section plus an install line."""
    tagged = _TAG.fullmatch(tag)
    if tagged is None:
        raise ValueError(f"tag {tag!r} isn't vMAJOR.MINOR.PATCH")
    version = tagged.group(1)
    section = changelog_section(changelog, version)
    if section is None:
        raise ValueError(f"CHANGELOG.md has no section for {version}")
    return (
        f"{section.strip()}\n\n"
        f"Install with `pip install mdxml=={version}`. Also on [PyPI](https://pypi.org/project/mdxml/{version}/).\n"
    )


def problems(tag: str, pyproject: str, changelog: str) -> list[str]:
    """Return every reason the tag can't be released."""
    found: list[str] = []
    tagged = _TAG.fullmatch(tag)
    if tagged is None:
        return [f"tag {tag!r} isn't vMAJOR.MINOR.PATCH (optionally with a1/b1/rc1)"]
    version = tagged.group(1)
    declared = project_version(pyproject)
    if declared != version:
        found.append(f"tag {tag!r} doesn't match pyproject.toml's version {declared!r}")
    section = changelog_section(changelog, version)
    if section is None:
        found.append(f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' section")
    elif not re.search(r"^- ", section, re.MULTILINE):
        found.append(f"CHANGELOG.md's section for {version} has no entries")
    return found


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--notes":
        try:
            print(release_notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), argv[1]), end="")
        except ValueError as exc:
            print(f"release notes: {exc}", file=sys.stderr)
            return 1
        return 0
    if len(argv) != 1:
        print("usage: check_release.py [--notes] vX.Y.Z", file=sys.stderr)
        return 2
    found = problems(
        argv[0],
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
    )
    for problem in found:
        print(f"release check: {problem}", file=sys.stderr)
    if not found:
        print(f"release check: {argv[0]} is ready")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
