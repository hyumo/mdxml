"""Issue #6: the full FMI 3 Model Header, with XSD defaults, lenient and strict modes."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import mdxml
from mdxml import ParseError, Source, UnsupportedFmiVersion, fmi3, to_dict
from mdxml.fmi3 import (
    BaseUnit,
    BinaryType,
    BooleanType,
    Category,
    ClockType,
    CoSimulation,
    DefaultExperiment,
    DisplayUnit,
    EnumerationType,
    Float32Type,
    Float64Type,
    Int8Type,
    Int16Type,
    Int32Type,
    Int64Type,
    IntervalVariability,
    Item,
    ModelExchange,
    ModelHeader,
    ScheduledExecution,
    StringType,
    UInt8Type,
    UInt16Type,
    UInt32Type,
    UInt64Type,
    Unit,
    VariableNamingConvention,
)

DATA = Path(__file__).parent / "data"
REFERENCE_FMI3 = sorted((DATA / "reference_fmus").glob("*/FMI3.xml"))
FULL = DATA / "fmi3" / "full_header.xml"


def read_header(src: Source, **options: Any) -> fmi3.ModelHeader:
    """Read an FMI 3 Model Header, narrowed to the FMI 3 type."""
    header = mdxml.read_header(src, **options)
    assert isinstance(header, fmi3.ModelHeader)
    return header


def header_xml(body: str, root_attrs: str = 'modelName="M" instantiationToken="t"', version: str = "3.0") -> bytes:
    return (
        f'<fmiModelDescription fmiVersion="{version}" {root_attrs}>{body}<ModelVariables/></fmiModelDescription>'
    ).encode()


# --- Complete headers -----------------------------------------------------------------------


def test_full_header_fixture() -> None:
    assert read_header(FULL) == ModelHeader(
        fmi_version="3.0",
        model_name="Full3",
        instantiation_token="{00000000-0000-0000-0000-000000000003}",
        description="Covers every FMI 3 Model Header element and attribute",
        author="mdxml tests",
        version="3.2.1",
        copyright="(c) nobody",
        license="MIT",
        generation_tool="hand",
        generation_date_and_time=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
        variable_naming_convention=VariableNamingConvention.STRUCTURED,
        model_exchange=ModelExchange(
            model_identifier="FullME",
            needs_execution_tool=True,
            can_be_instantiated_only_once_per_process=True,
            can_get_and_set_fmu_state=True,
            can_serialize_fmu_state=True,
            provides_directional_derivatives=True,
            provides_adjoint_derivatives=True,
            provides_per_element_dependencies=True,
            needs_completed_integrator_step=True,
            provides_evaluate_discrete_states=True,
        ),
        co_simulation=CoSimulation(
            model_identifier="FullCS",
            needs_execution_tool=True,
            can_be_instantiated_only_once_per_process=True,
            can_get_and_set_fmu_state=True,
            can_serialize_fmu_state=True,
            provides_directional_derivatives=True,
            provides_adjoint_derivatives=True,
            provides_per_element_dependencies=True,
            can_handle_variable_communication_step_size=True,
            fixed_internal_step_size=0.001,
            max_output_derivative_order=3,
            recommended_intermediate_input_smoothness=-1,
            provides_intermediate_update=True,
            might_return_early_from_do_step=True,
            can_return_early_after_intermediate_update=True,
            has_event_mode=True,
            provides_evaluate_discrete_states=True,
        ),
        scheduled_execution=ScheduledExecution(
            model_identifier="FullSE",
            needs_execution_tool=True,
            can_be_instantiated_only_once_per_process=True,
            can_get_and_set_fmu_state=True,
            can_serialize_fmu_state=True,
            provides_directional_derivatives=True,
            provides_adjoint_derivatives=True,
            provides_per_element_dependencies=True,
        ),
        unit_definitions=(
            Unit(
                name="degC",
                base_unit=BaseUnit(kg=1, m=2, s=-3, A=-1, K=1, mol=2, cd=3, rad=4, factor=1.5, offset=273.15),
                display_units=(
                    DisplayUnit(name="degF", factor=1.8, offset=32.0),
                    DisplayUnit(name="1/K", inverse=True),
                ),
            ),
            Unit(name="dimensionless"),
        ),
        type_definitions=(
            Float32Type(
                name="F32",
                description="single",
                quantity="Q",
                unit="degC",
                display_unit="degF",
                relative_quantity=True,
                unbounded=True,
                min=-1.5,
                max=1.5,
                nominal=0.5,
            ),
            Float64Type(name="F64", min=-math.inf, max=1e300, nominal=2.0),
            Int8Type(name="I8", quantity="Q", min=-128, max=127),
            UInt8Type(name="U8", min=0, max=255),
            Int16Type(name="I16", min=-32768, max=32767),
            UInt16Type(name="U16", min=0, max=65535),
            Int32Type(name="I32", min=-(2**31), max=2**31 - 1),
            UInt32Type(name="U32", min=0, max=2**32 - 1),
            Int64Type(name="I64", min=-(2**63), max=2**63 - 1),
            UInt64Type(name="U64", min=0, max=2**64 - 1),
            BooleanType(name="B", description="a flag"),
            StringType(name="S"),
            BinaryType(name="Bin", mime_type="image/png", max_size=1024),
            EnumerationType(
                name="Mode",
                description="Operating mode",
                quantity="Mode",
                min=0,
                max=1,
                items=(Item(name="off", value=0, description="Switched off"), Item(name="on", value=1)),
            ),
            ClockType(
                name="Clk",
                description="a clock",
                can_be_deactivated=True,
                priority=2,
                interval_variability=IntervalVariability.COUNTDOWN,
                interval_decimal=0.1,
                shift_decimal=0.05,
                supports_fraction=True,
                resolution=1000,
                interval_counter=100,
                shift_counter=50,
            ),
        ),
        log_categories=(Category(name="logAll", description="Everything"), Category(name="logNone")),
        default_experiment=DefaultExperiment(start_time=0.5, stop_time=10.0, tolerance=1e-6, step_size=0.01),
    )


def test_full_header_is_valid_in_strict_mode() -> None:
    assert read_header(FULL, strict=True) == read_header(FULL)


def test_integer_types_are_distinct_classes() -> None:
    # Same fields, different element: they must not compare equal.
    int8: object = Int8Type(name="x")
    float32: object = Float32Type(name="x")
    assert int8 != UInt8Type(name="x")
    assert float32 != Float64Type(name="x")


@pytest.mark.parametrize("path", REFERENCE_FMI3, ids=lambda p: p.parent.name)
def test_every_reference_header_parses_completely_in_strict_mode(path: Path) -> None:
    header = read_header(path, strict=True)
    assert header == read_header(path)
    assert header.instantiation_token.startswith("{")


def test_bouncing_ball_units_and_types() -> None:
    header = read_header(DATA / "reference_fmus" / "BouncingBall" / "FMI3.xml", strict=True)
    assert header.model_exchange is not None
    assert header.co_simulation is not None
    assert any(unit.display_units for unit in header.unit_definitions)
    assert all(isinstance(t, Float64Type) for t in header.type_definitions)


def test_clocks_has_scheduled_execution_only() -> None:
    header = read_header(DATA / "reference_fmus" / "Clocks" / "FMI3.xml", strict=True)
    assert header.scheduled_execution == ScheduledExecution(model_identifier="Clocks")
    assert header.model_exchange is None
    assert header.co_simulation is None


def test_feedthrough_enumeration_type() -> None:
    header = read_header(DATA / "reference_fmus" / "Feedthrough" / "FMI3.xml", strict=True)
    enums = [t for t in header.type_definitions if isinstance(t, EnumerationType)]
    assert [item.name for item in enums[0].items] == ["Option 1", "Option 2"]


# --- fmiVersion -----------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["3.0", "3.1", "3.0.1", "3.0-beta.2", "3.12.4-rc1"])
def test_fmi3_versions_are_accepted_in_both_modes(version: str) -> None:
    for strict in (False, True):
        assert read_header(header_xml("", version=version), strict=strict).fmi_version == version


@pytest.mark.parametrize("version", ["3", "3.01", "3.x"])
def test_off_pattern_fmi3_versions_are_lenient_only(version: str) -> None:
    assert read_header(header_xml("", version=version)).fmi_version == version
    with pytest.raises(ParseError, match="FMI 3 version pattern"):
        read_header(header_xml("", version=version), strict=True)


@pytest.mark.parametrize("version", ["4.0", "1.0"])
def test_other_major_versions_are_unsupported(version: str) -> None:
    with pytest.raises(UnsupportedFmiVersion):
        mdxml.read_header(header_xml("", version=version))


# --- XSD defaults ---------------------------------------------------------------------------


def test_xsd_defaults_are_applied() -> None:
    header = read_header(
        header_xml(
            '<CoSimulation modelIdentifier="cs"/>'
            '<UnitDefinitions><Unit name="u"><DisplayUnit name="d"/></Unit></UnitDefinitions>'
            "<TypeDefinitions>"
            '<BinaryType name="b"/><ClockType name="c" intervalVariability="fixed"/><Float64Type name="f"/>'
            "</TypeDefinitions>"
        )
    )
    assert header.variable_naming_convention is VariableNamingConvention.FLAT
    assert header.co_simulation == CoSimulation(model_identifier="cs")
    cs = header.co_simulation
    assert cs is not None
    assert (cs.max_output_derivative_order, cs.recommended_intermediate_input_smoothness) == (0, 0)
    assert cs.fixed_internal_step_size is None
    assert header.unit_definitions[0].display_units == (DisplayUnit(name="d", factor=1.0, offset=0.0, inverse=False),)
    binary, clock, real = header.type_definitions
    assert binary == BinaryType(name="b", mime_type="application/octet-stream", max_size=None)
    assert isinstance(clock, ClockType)
    assert (clock.shift_decimal, clock.shift_counter, clock.can_be_deactivated) == (0.0, 0, False)
    assert real == Float64Type(name="f", relative_quantity=False, unbounded=False)


def test_annotations_are_skipped_everywhere_even_in_strict_mode() -> None:
    xml = header_xml(
        '<ScheduledExecution modelIdentifier="s"><Annotations><Annotation type="t"><X/></Annotation>'
        "</Annotations></ScheduledExecution>"
    )
    assert read_header(xml, strict=True).scheduled_execution == ScheduledExecution(model_identifier="s")


# --- Lenient vs strict ----------------------------------------------------------------------

LENIENT_FIXTURES = {
    "unknown attribute": (header_xml('<LogCategories><Category name="c" color="red"/></LogCategories>'), "color"),
    "unknown element": (header_xml("<Extensions><Something/></Extensions>"), "<Extensions>"),
    "unknown type definition": (header_xml('<TypeDefinitions><Int128Type name="x"/></TypeDefinitions>'), "Int128Type"),
    "boolean in other case": (header_xml('<CoSimulation modelIdentifier="cs" hasEventMode="TRUE"/>'), "hasEventMode"),
    "unknown enum value": (
        header_xml("", 'modelName="M" instantiationToken="t" variableNamingConvention="dotted"'),
        "variableNamingConvention",
    ),
    "unknown clock interval variability": (
        header_xml('<TypeDefinitions><ClockType name="c" intervalVariability="sometimes"/></TypeDefinitions>'),
        "intervalVariability",
    ),
    "integer out of range": (
        header_xml('<TypeDefinitions><Int8Type name="i" max="200"/></TypeDefinitions>'),
        "xs:byte",
    ),
    "negative unsigned": (header_xml('<TypeDefinitions><UInt16Type name="u" min="-1"/></TypeDefinitions>'), "min"),
    "missing required attribute": (header_xml("<UnitDefinitions><Unit/></UnitDefinitions>"), "'name'"),
    "missing instantiationToken": (header_xml("", 'modelName="M"'), "instantiationToken"),
    "two ScheduledExecutions": (
        header_xml('<ScheduledExecution modelIdentifier="a"/><ScheduledExecution modelIdentifier="b"/>'),
        "ScheduledExecution",
    ),
}


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_lenient_fixture_parses(case: str) -> None:
    xml, _ = LENIENT_FIXTURES[case]
    assert read_header(xml).model_name == "M"


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_same_fixture_raises_in_strict_mode(case: str) -> None:
    xml, message = LENIENT_FIXTURES[case]
    with pytest.raises(ParseError, match=message):
        read_header(xml, strict=True)


def test_lenient_values() -> None:
    header = read_header(
        header_xml(
            '<CoSimulation modelIdentifier="cs" hasEventMode="TRUE"/>'
            '<TypeDefinitions><Int8Type name="i" min="-1" max="200"/>'
            '<ClockType name="c" intervalVariability="sometimes"/></TypeDefinitions>',
            'modelName="M"',
        )
    )
    assert header.instantiation_token == ""
    assert header.co_simulation == CoSimulation(model_identifier="cs", has_event_mode=True)
    int8, clock = header.type_definitions
    assert int8 == Int8Type(name="i", min=-1)  # out-of-range max dropped
    assert isinstance(clock, ClockType)
    assert clock.interval_variability == "sometimes"


@pytest.mark.parametrize("strict", [False, True])
def test_clock_without_interval_variability_raises_in_both_modes(strict: bool) -> None:
    # A required attribute with no lenient fallback can't be built.
    with pytest.raises(ParseError, match="intervalVariability"):
        read_header(header_xml('<TypeDefinitions><ClockType name="c"/></TypeDefinitions>'), strict=strict)


@pytest.mark.parametrize("strict", [False, True])
def test_item_value_out_of_long_range_raises_in_both_modes(strict: bool) -> None:
    xml = header_xml(
        '<TypeDefinitions><EnumerationType name="e"><Item name="a" value="9223372036854775808"/>'
        "</EnumerationType></TypeDefinitions>"
    )
    with pytest.raises(ParseError, match="xs:long"):
        read_header(xml, strict=strict)


# --- Stops at <ModelVariables>, so the trailing Annotations are never read ------------------


def test_trailing_annotations_are_never_reached() -> None:
    data = FULL.read_bytes()
    cut = data.index(b"<ModelVariables>") + len(b"<ModelVariables>")
    broken = data[:cut] + b"<<< not xml &&& </nope>"
    assert read_header(broken, strict=True) == read_header(FULL)


# --- Output ---------------------------------------------------------------------------------


def test_to_dict_and_cli(capsys: pytest.CaptureFixture[str]) -> None:
    data = to_dict(read_header(FULL))
    json.dumps(data, allow_nan=False)
    assert data["type_definitions"][1] == {
        "name": "F64",
        "relative_quantity": False,
        "unbounded": False,
        "min": "-INF",
        "max": 1e300,
        "nominal": 2.0,
    }
    assert data["type_definitions"][-1]["interval_variability"] == "countdown"

    assert mdxml.main(["header", str(FULL), "--strict"]) == 0
    assert json.loads(capsys.readouterr().out)["instantiation_token"] == "{00000000-0000-0000-0000-000000000003}"
