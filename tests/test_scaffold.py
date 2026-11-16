"""Sanity checks for the project scaffold and the committed test data."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from importlib import resources
from pathlib import Path

import pytest

import mdxml

REFERENCE_FMUS = Path(__file__).parent / "data" / "reference_fmus"
REFERENCE_XMLS = sorted(REFERENCE_FMUS.glob("*/FMI[23].xml"))


def test_package_is_typed() -> None:
    assert resources.files(mdxml).joinpath("py.typed").is_file()


def test_reference_data_covers_both_fmi_versions() -> None:
    names = {p.name for p in REFERENCE_XMLS}
    assert names == {"FMI2.xml", "FMI3.xml"}


@pytest.mark.parametrize("path", REFERENCE_XMLS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_reference_data_is_a_model_description(path: Path) -> None:
    root = ET.parse(path).getroot()
    assert root.tag == "fmiModelDescription"
    expected_major = path.stem.removeprefix("FMI")
    assert root.get("fmiVersion", "").startswith(expected_major + ".")
