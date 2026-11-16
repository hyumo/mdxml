"""The README's examples run, and print what their comments say."""

from __future__ import annotations

import contextlib
import io
import re
import shlex
import zipfile
from pathlib import Path

import pytest

import mdxml

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
BOUNCING_BALL = ROOT / "tests" / "data" / "reference_fmus" / "BouncingBall" / "FMI3.xml"

PYTHON_BLOCKS = re.findall(r"```python\n(.*?)```", README, re.DOTALL)
SHELL_BLOCKS = re.findall(r"```sh\n(.*?)```", README, re.DOTALL)


@pytest.fixture
def in_folder_with_fmu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    with zipfile.ZipFile(tmp_path / "BouncingBall.fmu", "w", zipfile.ZIP_DEFLATED) as fmu:
        fmu.write(BOUNCING_BALL, "modelDescription.xml")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(code: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "README.md", "exec"), {"__name__": "readme"})
    return out.getvalue()


def test_the_readme_has_examples() -> None:
    assert len(PYTHON_BLOCKS) >= 8


@pytest.mark.parametrize("code", PYTHON_BLOCKS, ids=[f"block{i}" for i in range(len(PYTHON_BLOCKS))])
@pytest.mark.usefixtures("in_folder_with_fmu")
def test_every_python_example_runs(code: str) -> None:
    run(code)


@pytest.mark.usefixtures("in_folder_with_fmu")
def test_printed_values_match_the_comments() -> None:
    for code in PYTHON_BLOCKS:
        lines = run(code).splitlines()
        promised = [
            comment.strip()
            for line in code.splitlines()
            if line.lstrip().startswith("print(")
            and (comment := line.partition("#")[2].strip())
            and not comment[0].islower()  # explanatory comments start lowercase; values don't
        ]
        for value in promised:
            assert any(value in line for line in lines), f"{value!r} not printed by:\n{code}"


@pytest.mark.usefixtures("in_folder_with_fmu")
def test_cli_examples_run(capsys: pytest.CaptureFixture[str]) -> None:
    commands = [
        shlex.split(line.partition("#")[0])
        for block in SHELL_BLOCKS
        for line in block.splitlines()
        if line.startswith("mdxml ") and "BouncingBall.fmu" in line
    ]
    assert len(commands) >= 2
    for command in commands:
        assert mdxml.main(command[1:]) == 0, command
        assert capsys.readouterr().out
