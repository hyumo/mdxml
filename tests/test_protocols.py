"""Issue #10: version-independent Protocols for headers and variables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import mdxml
from mdxml import InterfaceType, ModelHeader, ModelVariable, fmi2, fmi3, iter_variables, read_header

DATA = Path(__file__).parent / "data"
REFERENCES = sorted((DATA / "reference_fmus").glob("*/FMI[23].xml"))


# --- Static conformance: mypy and pyright (strict) check these assignments -----------------


def fmi2_header(header: fmi2.ModelHeader) -> ModelHeader:
    return header


def fmi3_header(header: fmi3.ModelHeader) -> ModelHeader:
    return header


def any_header(header: mdxml.AnyModelHeader) -> ModelHeader:
    return header


def fmi2_interfaces(me: fmi2.ModelExchange, cs: fmi2.CoSimulation) -> tuple[InterfaceType, InterfaceType]:
    return me, cs


def fmi3_interfaces(me: fmi3.ModelExchange, cs: fmi3.CoSimulation) -> tuple[InterfaceType, InterfaceType]:
    return me, cs


def fmi2_variable(variable: fmi2.Variable) -> ModelVariable:
    """Covers every FMI 2 variable class: the union lists all of them."""
    return variable


def fmi3_variable(variable: fmi3.Variable) -> ModelVariable:
    """Covers every FMI 3 variable class, including ClockVariable."""
    return variable


def any_variable(variable: mdxml.AnyVariable) -> ModelVariable:
    return variable


def a_unit_is_not_a_header() -> ModelHeader:
    # mypy (strict) reports unused ignores, so this proves the checker would catch a mismatch.
    return fmi2.Unit(name="m")  # type: ignore[return-value]  # pyright: ignore[reportReturnType]


# --- A version-independent function ---------------------------------------------------------


def summarize(header: ModelHeader, variables: list[ModelVariable]) -> dict[str, Any]:
    """Written once against the Protocols; works for either FMI Version."""
    interfaces = [i.model_identifier for i in (header.model_exchange, header.co_simulation) if i is not None]
    return {
        "model": header.model_name,
        "token": header.instantiation_token,
        "interfaces": interfaces,
        "outputs": [v.name for v in variables if v.causality == "output"],
        "continuous": sorted(v.name for v in variables if v.variability == "continuous"),
        "indexes_are_positions": [v.index for v in variables] == list(range(1, len(variables) + 1)),
    }


def summarize_file(path: Path) -> dict[str, Any]:
    variables = iter_variables(path)
    return summarize(variables.header, list(variables))


@pytest.mark.parametrize("path", REFERENCES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_version_independent_function_works_on_every_reference(path: Path) -> None:
    summary = summarize_file(path)
    assert summary["model"]
    assert summary["token"].startswith("{")
    assert summary["indexes_are_positions"]


def test_same_model_gives_the_same_summary_in_both_versions() -> None:
    fmi2_summary = summarize_file(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    fmi3_summary = summarize_file(DATA / "reference_fmus" / "BouncingBall" / "FMI3.xml")
    assert fmi2_summary["outputs"] == fmi3_summary["outputs"] == ["h", "v"]
    assert fmi2_summary["continuous"] == fmi3_summary["continuous"]
    assert fmi2_summary["interfaces"] == fmi3_summary["interfaces"] == ["BouncingBall", "BouncingBall"]


# --- Runtime --------------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_runtime_isinstance(path: Path) -> None:
    header = read_header(path)
    assert isinstance(header, ModelHeader)
    for interface in (header.model_exchange, header.co_simulation):
        if interface is not None:
            assert isinstance(interface, InterfaceType)
    for variable in iter_variables(path):
        assert isinstance(variable, ModelVariable)


def test_fmi2_guid_is_the_instantiation_token() -> None:
    header = read_header(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    assert isinstance(header, fmi2.ModelHeader)
    assert header.instantiation_token == header.guid == "{1AE5E10D-9521-4DE3-80B9-D0EAAA7D5AF1}"
    # It's a property, not a field: to_dict keeps the FMI 2 name only.
    assert "instantiation_token" not in mdxml.to_dict(header)


def test_versions_do_not_inherit_from_each_other_or_the_protocols() -> None:
    assert not issubclass(fmi2.ModelHeader, fmi3.ModelHeader)
    assert not issubclass(fmi3.ModelHeader, fmi2.ModelHeader)
    for cls in (fmi2.ModelHeader, fmi3.ModelHeader, fmi2.RealVariable, fmi3.Float64Variable):
        assert ModelHeader not in cls.__mro__
        assert ModelVariable not in cls.__mro__


def test_things_that_are_not_headers_or_variables() -> None:
    assert not isinstance(fmi2.Unit(name="m"), ModelHeader)
    assert not isinstance(fmi3.Category(name="c"), ModelVariable)
