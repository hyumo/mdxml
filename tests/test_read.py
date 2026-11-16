"""Issue #9: read() returns the whole Model Description, including the Model Structure."""

from __future__ import annotations

import json
import tracemalloc
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

import mdxml
from mdxml import ParseError, Source, fmi2, fmi3, iter_variables, read, read_header, to_dict

DATA = Path(__file__).parent / "data"
REFERENCES = sorted((DATA / "reference_fmus").glob("*/FMI[23].xml"))
STRUCTURE3 = DATA / "fmi3" / "structure.xml"


def read2(src: Source, **options: Any) -> fmi2.ModelDescription:
    md = read(src, **options)
    assert isinstance(md, fmi2.ModelDescription)
    return md


def read3(src: Source, **options: Any) -> fmi3.ModelDescription:
    md = read(src, **options)
    assert isinstance(md, fmi3.ModelDescription)
    return md


def fmi2_model(structure: str, variables: int = 3) -> bytes:
    scalars = "".join(
        f'<ScalarVariable name="v{i}" valueReference="{i}"><Real/></ScalarVariable>' for i in range(1, variables + 1)
    )
    return (
        '<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g">'
        f"<ModelVariables>{scalars}</ModelVariables>{structure}</fmiModelDescription>"
    ).encode()


# --- read() agrees with read_header and iter_variables --------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_read_agrees_with_read_header_and_iter_variables(path: Path) -> None:
    md = read(path, strict=True)
    assert md.header == read_header(path)
    assert md.variables == tuple(iter_variables(path))


# --- The Model Structure, checked against an independent ElementTree reading ---------------


def _unknown_from(element: ET.Element, key: str) -> dict[str, Any]:
    dependencies = element.get("dependencies")
    kinds = element.get("dependenciesKind")
    return {
        key: int(element.get(key, "-1")),
        "dependencies": None if dependencies is None else tuple(int(d) for d in dependencies.split()),
        "dependencies_kind": None if kinds is None else tuple(kinds.split()),
    }


def expected_structure(path: Path) -> dict[str, list[dict[str, Any]]]:
    root = ET.parse(path).getroot()
    structure = root.find("ModelStructure")
    assert structure is not None
    if root.get("fmiVersion", "").startswith("2"):
        return {
            field: [_unknown_from(u, "index") for u in structure.findall(f"{tag}/Unknown")]
            for tag, field in (
                ("Outputs", "outputs"),
                ("Derivatives", "derivatives"),
                ("InitialUnknowns", "initial_unknowns"),
            )
        }
    return {
        field: [_unknown_from(u, "valueReference") for u in structure.findall(tag)]
        for tag, field in (
            ("Output", "outputs"),
            ("ContinuousStateDerivative", "continuous_state_derivatives"),
            ("ClockedState", "clocked_states"),
            ("InitialUnknown", "initial_unknowns"),
            ("EventIndicator", "event_indicators"),
        )
    }


def actual_structure(md: mdxml.AnyModelDescription) -> dict[str, list[dict[str, Any]]]:
    data = to_dict(md.model_structure)
    out: dict[str, list[dict[str, Any]]] = {}
    for field, unknowns in data.items():
        out[field] = [
            {
                **{k: v for k, v in unknown.items() if k in {"index", "value_reference"}},
                "dependencies": None if "dependencies" not in unknown else tuple(unknown["dependencies"]),
                "dependencies_kind": None
                if "dependencies_kind" not in unknown
                else tuple(unknown["dependencies_kind"]),
            }
            for unknown in unknowns
        ]
    return {field: [_rename_key(u) for u in unknowns] for field, unknowns in out.items()}


def _rename_key(unknown: dict[str, Any]) -> dict[str, Any]:
    if "value_reference" in unknown:
        return {"valueReference": unknown.pop("value_reference"), **unknown}
    return unknown


@pytest.mark.parametrize("path", REFERENCES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_model_structure_matches_an_independent_reading(path: Path) -> None:
    assert actual_structure(read(path, strict=True)) == expected_structure(path)


def test_bouncing_ball_fmi2_structure() -> None:
    md = read2(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    structure = md.model_structure
    assert [u.index for u in structure.outputs] == [2, 4]
    assert structure.outputs[0].dependencies == ()  # present but empty: depends on nothing
    derivative = structure.derivatives[0]
    assert derivative == fmi2.Unknown(index=3, dependencies=(4,), dependencies_kind=(fmi2.DependenciesKind.CONSTANT,))
    assert md.variable_by_index(derivative.index).name == "der(h)"
    assert md.variable_by_index(derivative.dependencies[0]).name == "v"  # type: ignore[index]


def test_fmi3_structure_fixture() -> None:
    md = read3(STRUCTURE3, strict=True)
    structure = md.model_structure
    kind = fmi3.DependenciesKind
    assert structure == fmi3.ModelStructure(
        outputs=(
            fmi3.Unknown(value_reference=3, dependencies=(1, 7), dependencies_kind=(kind.DEPENDENT, kind.CONSTANT)),
        ),
        continuous_state_derivatives=(fmi3.Unknown(value_reference=2, dependencies=(1,)),),
        clocked_states=(fmi3.Unknown(value_reference=5, dependencies=()),),
        initial_unknowns=(
            fmi3.Unknown(value_reference=3),
            fmi3.Unknown(value_reference=2, dependencies=(1,), dependencies_kind=(kind.FIXED,)),
        ),
        event_indicators=(fmi3.Unknown(value_reference=7, dependencies=(1,), dependencies_kind=(kind.DISCRETE,)),),
    )
    assert structure.initial_unknowns[0].dependencies is None  # absent: may depend on all knowns
    assert md.variable_by_value_reference(structure.outputs[0].value_reference).name == "y"


def test_trailing_annotations_are_skipped_even_in_strict_mode() -> None:
    assert len(read3(STRUCTURE3, strict=True).variables) == 8


# --- Lookup helpers -------------------------------------------------------------------------


def test_header_definitions_by_name() -> None:
    header = read2(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml").header
    assert header.type_definitions["Velocity"].name == "Velocity"
    assert header.unit_definitions["m/s2"].base_unit == fmi2.BaseUnit(m=1, s=-2)
    assert header.log_categories["logEvents"].description == "Log events"
    assert header.type_definitions[0].name == "Position"  # still a tuple
    assert header.type_definitions[:2] == header.type_definitions[0:2]
    # Named overrides `in` to accept names; mypy's strict-equality check doesn't see that.
    assert "Velocity" in header.type_definitions  # type: ignore[comparison-overlap]
    assert "Nope" not in header.type_definitions  # type: ignore[comparison-overlap]
    assert header.unit_definitions.get("nope") is None
    with pytest.raises(KeyError):
        header.type_definitions["Nope"]
    with pytest.raises(KeyError):
        header.unit_definitions["nope"]


def test_fmi3_header_definitions_by_name() -> None:
    header = read3(DATA / "reference_fmus" / "Feedthrough" / "FMI3.xml").header
    option = header.type_definitions["Option"]
    assert isinstance(option, fmi3.EnumerationType)
    assert [item.value for item in option.items] == [1, 2]


def test_named_compares_equal_to_plain_tuples() -> None:
    header = read_header(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    assert header.log_categories == tuple(header.log_categories)
    assert isinstance(header.log_categories, mdxml.Named)


def test_fmi2_variable_lookups() -> None:
    md = read2(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    assert md.variable_by_name("h").value_reference == 1
    assert md.variable_by_value_reference(1).name == "h"
    assert md.variable_by_value_reference(1, type_name="Real").name == "h"
    assert md.variable_by_index(1).name == "time"
    with pytest.raises(KeyError):
        md.variable_by_name("nope")
    with pytest.raises(KeyError):
        md.variable_by_value_reference(999)
    with pytest.raises(KeyError):
        md.variable_by_value_reference(1, type_name="Integer")
    with pytest.raises(KeyError):
        md.variable_by_index(0)
    with pytest.raises(KeyError):
        md.variable_by_index(len(md.variables) + 1)


def test_fmi2_value_references_are_per_type_and_shared_by_aliases() -> None:
    xml = (
        b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g"><ModelVariables>'
        b'<ScalarVariable name="r" valueReference="1"><Real/></ScalarVariable>'
        b'<ScalarVariable name="r_alias" valueReference="1"><Real/></ScalarVariable>'
        b'<ScalarVariable name="i" valueReference="1"><Integer/></ScalarVariable>'
        b"</ModelVariables><ModelStructure/></fmiModelDescription>"
    )
    md = read2(xml)
    assert md.variable_by_value_reference(1).name == "r"  # first in file order
    assert md.variable_by_value_reference(1, type_name="Integer").name == "i"
    assert md.variable_by_name("r_alias").value_reference == 1


def test_fmi3_variable_lookups() -> None:
    md = read3(STRUCTURE3)
    assert md.variable_by_value_reference(4).type_name == "Clock"
    assert md.variable_by_name("der(x)").value_reference == 2
    with pytest.raises(KeyError):
        md.variable_by_value_reference(99)
    with pytest.raises(KeyError):
        md.variable_by_name("nope")


def test_lookups_are_not_part_of_equality_or_output() -> None:
    md = read2(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    same = fmi2.ModelDescription(header=md.header, variables=md.variables, model_structure=md.model_structure)
    assert same == md
    data = to_dict(md)
    assert set(data) == {"header", "variables", "model_structure"}
    json.dumps(data, allow_nan=False)


# --- Lenient vs strict ----------------------------------------------------------------------

LENIENT_FIXTURES = {
    "dependenciesKind without dependencies": (
        fmi2_model('<ModelStructure><Outputs><Unknown index="1" dependenciesKind="fixed"/></Outputs></ModelStructure>'),
        "dependenciesKind",
    ),
    "list lengths differ": (
        fmi2_model(
            "<ModelStructure><Outputs>"
            '<Unknown index="1" dependencies="2 3" dependenciesKind="fixed"/>'
            "</Outputs></ModelStructure>"
        ),
        "dependenciesKind",
    ),
    "unknown dependency kind": (
        fmi2_model(
            '<ModelStructure><Outputs><Unknown index="1" dependencies="2" dependenciesKind="sometimes"/>'
            "</Outputs></ModelStructure>"
        ),
        "dependenciesKind",
    ),
    "unknown element in ModelStructure": (fmi2_model("<ModelStructure><Extra/></ModelStructure>"), "<Extra>"),
    "unknown element after ModelVariables": (fmi2_model("<ModelStructure/><Extra/>"), "<Extra>"),
    "missing ModelStructure": (fmi2_model(""), "no <ModelStructure>"),
    "two ModelStructures": (fmi2_model("<ModelStructure/><ModelStructure/>"), "<ModelStructure>"),
}


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_lenient_fixture_reads(case: str) -> None:
    xml, _ = LENIENT_FIXTURES[case]
    assert len(read2(xml).variables) == 3


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_same_fixture_raises_in_strict_mode(case: str) -> None:
    xml, message = LENIENT_FIXTURES[case]
    with pytest.raises(ParseError, match=message):
        read(xml, strict=True)


def test_missing_model_structure_is_empty_in_lenient_mode() -> None:
    assert read2(fmi2_model("")).model_structure == fmi2.ModelStructure()


@pytest.mark.parametrize("strict", [False, True])
def test_unknown_without_index_raises_in_both_modes(strict: bool) -> None:
    with pytest.raises(ParseError, match="'index'"):
        read(fmi2_model("<ModelStructure><Outputs><Unknown/></Outputs></ModelStructure>"), strict=strict)


# --- Memory: only parsed objects are kept ---------------------------------------------------


def test_read_keeps_less_than_an_element_tree(tmp_path: Path) -> None:
    path = tmp_path / "big.xml"
    with path.open("w", encoding="utf-8") as out:
        out.write('<fmiModelDescription fmiVersion="2.0" modelName="Big" guid="g"><ModelVariables>')
        for i in range(10_000):
            out.write(
                f'<ScalarVariable name="v{i}" valueReference="{i}" causality="output" description="variable {i}">'
                f'<Real start="{i}.5" unit="m"/></ScalarVariable>'
            )
        out.write("</ModelVariables><ModelStructure/></fmiModelDescription>")

    def peak(load: Any) -> tuple[Any, int]:
        tracemalloc.start()
        try:
            result = load()
            _, top = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        return result, top

    md, read_peak = peak(lambda: read(path))
    _, tree_peak = peak(lambda: ET.parse(path))
    assert len(md.variables) == 10_000
    assert read_peak < tree_peak
