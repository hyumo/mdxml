"""Issue #14: the release check and the built wheel."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parent.parent


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_release = load("check_release")
check_wheel = load("check_wheel")

PYPROJECT = '[project]\nname = "mdxml"\nversion = "1.2.3"\n\n[tool.other]\nversion = "9.9.9"\n'
CHANGELOG = """# Changelog

## [Unreleased]

## [1.2.3] - 2026-11-16

### Added

- Something new.

## [1.2.2] - 2026-10-01

- Older.
"""


def test_a_ready_release_has_no_problems() -> None:
    assert check_release.problems("v1.2.3", PYPROJECT, CHANGELOG) == []


@pytest.mark.parametrize(
    ("tag", "pyproject", "changelog", "problem"),
    [
        ("1.2.3", PYPROJECT, CHANGELOG, "isn't vMAJOR.MINOR.PATCH"),
        ("v1.2", PYPROJECT, CHANGELOG, "isn't vMAJOR.MINOR.PATCH"),
        ("v1.2.4", PYPROJECT, CHANGELOG.replace("1.2.3", "1.2.4"), "doesn't match pyproject.toml's version '1.2.3'"),
        ("v1.2.3", PYPROJECT, CHANGELOG.replace("[1.2.3] - 2026-11-16", "[1.2.3]"), "no '## [1.2.3] - YYYY-MM-DD'"),
        ("v1.2.3", PYPROJECT, CHANGELOG.replace("## [1.2.3]", "## [1.2.9]"), "no '## [1.2.3] - YYYY-MM-DD'"),
        ("v1.2.3", PYPROJECT, CHANGELOG.replace("- Something new.\n", ""), "has no entries"),
    ],
)
def test_release_problems(tag: str, pyproject: str, changelog: str, problem: str) -> None:
    found = check_release.problems(tag, pyproject, changelog)
    assert any(problem in p for p in found), found


def test_only_the_project_version_counts() -> None:
    assert check_release.project_version(PYPROJECT) == "1.2.3"


def test_pre_release_tags_are_accepted() -> None:
    pyproject = PYPROJECT.replace('"1.2.3"', '"1.3.0rc1"')
    changelog = CHANGELOG.replace("1.2.3", "1.3.0rc1")
    assert check_release.problems("v1.3.0rc1", pyproject, changelog) == []


def test_the_real_project_version_is_found() -> None:
    assert check_release.project_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(out), str(ROOT)], check=True, capture_output=True)
    (path,) = out.glob("*.whl")
    return path


def test_the_built_wheel_passes_the_wheel_check(wheel: Path) -> None:
    assert check_wheel.check(str(wheel)) == []


def test_the_wheel_check_catches_xsd_files_and_dependencies(wheel: Path, tmp_path: Path) -> None:
    bad = tmp_path / wheel.name
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(bad, "w") as target:
        for item in source.infolist():
            data = source.read(item)
            if item.filename.endswith(".dist-info/METADATA"):
                # Headers end at the first blank line (the README follows as the description).
                data = data.replace(b"\n", b"\nRequires-Dist: lxml\n", 1)
            target.writestr(item, data)
        target.writestr("mdxml/schema/fmi2ModelDescription.xsd", b"<xs:schema/>")
    found = check_wheel.check(str(bad))
    assert any("XSD file shipped" in p for p in found)
    assert any("runtime dependency declared: lxml" in p for p in found)


def test_the_release_check_script_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release.py"), "not-a-tag"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "isn't vMAJOR.MINOR.PATCH" in result.stderr


def test_release_notes_are_the_changelog_section() -> None:
    notes = check_release.release_notes(CHANGELOG, "v1.2.3")
    assert notes.startswith("### Added\n\n- Something new.")
    assert "Older." not in notes  # stops at the next version
    assert "pip install mdxml==1.2.3" in notes
    assert notes.endswith("https://pypi.org/project/mdxml/1.2.3/).\n")


@pytest.mark.parametrize(("tag", "message"), [("1.2.3", "isn't vMAJOR"), ("v9.9.9", "no section for 9.9.9")])
def test_release_notes_need_a_valid_tag_and_section(tag: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        check_release.release_notes(CHANGELOG, tag)


def test_release_notes_for_the_real_changelog() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release.py"), "--notes", "v0.1.0"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.startswith("First release:")
    assert "pip install mdxml==0.1.0" in result.stdout
