"""Issue #5: the full FMI 2 Model Header, with XSD defaults, lenient and strict modes."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import mdxml
from mdxml import ParseError, Source, fmi2
from mdxml._lookup import Named
from mdxml.fmi2 import (
    BaseUnit,
    BooleanType,
    Category,
    CoSimulation,
    DefaultExperiment,
    DisplayUnit,
    EnumerationType,
    IntegerType,
    Item,
    ModelExchange,
    ModelHeader,
    RealType,
    StringType,
    Unit,
    VariableNamingConvention,
)

DATA = Path(__file__).parent / "data"
REFERENCE_FMI2 = sorted((DATA / "reference_fmus").glob("*/FMI2.xml"))
FULL = DATA / "fmi2" / "full_header.xml"


def read_header(src: Source, **options: Any) -> fmi2.ModelHeader:
    """Read an FMI 2 Model Header, narrowed to the FMI 2 type."""
    header = mdxml.read_header(src, **options)
    assert isinstance(header, fmi2.ModelHeader)
    return header


def header_xml(body: str, root_attrs: str = 'modelName="M" guid="g"') -> bytes:
    return (
        f'<fmiModelDescription fmiVersion="2.0" {root_attrs}>{body}<ModelVariables/></fmiModelDescription>'
    ).encode()


# --- Complete headers -----------------------------------------------------------------------


def test_full_header_fixture() -> None:
    assert read_header(FULL) == ModelHeader(
        fmi_version="2.0",
        model_name="Full",
        guid="{00000000-0000-0000-0000-000000000001}",
        description="Covers every Model Header element and attribute",
        author="mdxml tests",
        version="1.2.3",
        copyright="(c) nobody",
        license="MIT",
        generation_tool="hand",
        generation_date_and_time=datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
        variable_naming_convention=VariableNamingConvention.STRUCTURED,
        number_of_event_indicators=4,
        model_exchange=ModelExchange(
            model_identifier="FullME",
            needs_execution_tool=True,
            completed_integrator_step_not_needed=True,
            can_be_instantiated_only_once_per_process=True,
            can_not_use_memory_management_functions=True,
            can_get_and_set_fmu_state=True,
            can_serialize_fmu_state=True,
            provides_directional_derivative=True,
            source_files=("a.c", "b.c"),
        ),
        co_simulation=CoSimulation(
            model_identifier="FullCS",
            needs_execution_tool=True,
            can_handle_variable_communication_step_size=True,
            can_interpolate_inputs=True,
            max_output_derivative_order=2,
            can_run_asynchronuously=True,
            can_be_instantiated_only_once_per_process=True,
            can_not_use_memory_management_functions=True,
            can_get_and_set_fmu_state=True,
            can_serialize_fmu_state=True,
            provides_directional_derivative=True,
        ),
        unit_definitions=Named(
            (
                Unit(
                    name="degC",
                    base_unit=BaseUnit(kg=1, m=2, s=-3, A=-1, K=1, mol=2, cd=3, rad=4, factor=1.5, offset=273.15),
                    display_units=(DisplayUnit(name="degF", factor=1.8, offset=32.0), DisplayUnit(name="K2")),
                ),
                Unit(name="dimensionless"),
            )
        ),
        type_definitions=Named(
            (
                RealType(
                    name="Temp",
                    description="A temperature",
                    quantity="ThermodynamicTemperature",
                    unit="degC",
                    display_unit="degF",
                    relative_quantity=True,
                    min=-273.15,
                    max=math.inf,
                    nominal=300.0,
                    unbounded=True,
                ),
                IntegerType(name="Count", quantity="Count", min=-5, max=5),
                BooleanType(name="Flag"),
                StringType(name="Label"),
                EnumerationType(
                    name="Mode",
                    description="Operating mode",
                    quantity="Mode",
                    items=(Item(name="off", value=0, description="Switched off"), Item(name="on", value=1)),
                ),
            )
        ),
        log_categories=Named((Category(name="logAll", description="Everything"), Category(name="logNone"))),
        default_experiment=DefaultExperiment(start_time=0.5, stop_time=10.0, tolerance=1e-6, step_size=0.01),
    )


def test_full_header_is_valid_in_strict_mode() -> None:
    assert read_header(FULL, strict=True) == read_header(FULL)


def test_bouncing_ball_complete_header() -> None:
    header = read_header(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")

    assert header.model_exchange == ModelExchange(
        model_identifier="BouncingBall",
        completed_integrator_step_not_needed=True,
        can_not_use_memory_management_functions=True,
        can_get_and_set_fmu_state=True,
        can_serialize_fmu_state=True,
        source_files=("all.c",),
    )
    assert header.co_simulation == CoSimulation(
        model_identifier="BouncingBall",
        can_handle_variable_communication_step_size=True,
        can_not_use_memory_management_functions=True,
        can_get_and_set_fmu_state=True,
        can_serialize_fmu_state=True,
        source_files=("all.c",),
    )
    assert header.unit_definitions == (
        Unit(name="m", base_unit=BaseUnit(m=1)),
        Unit(name="m/s", base_unit=BaseUnit(m=1, s=-1)),
        Unit(name="m/s2", base_unit=BaseUnit(m=1, s=-2)),
    )
    assert header.type_definitions == (
        RealType(name="Position", quantity="Position", unit="m"),
        RealType(name="Velocity", quantity="Velocity", unit="m/s"),
        RealType(name="Acceleration", quantity="Acceleration", unit="m/s2"),
    )
    assert header.log_categories == (
        Category(name="logEvents", description="Log events"),
        Category(name="logStatusError", description="Log error messages"),
    )
    assert header.default_experiment == DefaultExperiment(start_time=0.0, stop_time=3.0, step_size=0.01)


def test_feedthrough_enumeration_type() -> None:
    header = read_header(DATA / "reference_fmus" / "Feedthrough" / "FMI2.xml")
    assert header.type_definitions == (
        EnumerationType(
            name="Option",
            items=(
                Item(name="Option 1", value=1, description="First option"),
                Item(name="Option 2", value=2, description="Second option"),
            ),
        ),
    )


@pytest.mark.parametrize("path", REFERENCE_FMI2, ids=lambda p: p.parent.name)
def test_every_reference_header_parses_completely_in_strict_mode(path: Path) -> None:
    # Strict mode raises on anything unknown, so passing means nothing was skipped.
    header = read_header(path, strict=True)
    assert header == read_header(path)
    assert header.model_exchange is not None or header.co_simulation is not None


# --- XSD defaults ---------------------------------------------------------------------------


def test_xsd_defaults_are_applied() -> None:
    header = read_header(
        header_xml(
            '<ModelExchange modelIdentifier="me"/>'
            '<CoSimulation modelIdentifier="cs"/>'
            '<UnitDefinitions><Unit name="u"><BaseUnit/><DisplayUnit name="d"/></Unit></UnitDefinitions>'
            '<TypeDefinitions><SimpleType name="r"><Real/></SimpleType></TypeDefinitions>'
        )
    )

    assert header.variable_naming_convention is VariableNamingConvention.FLAT
    assert header.model_exchange == ModelExchange(model_identifier="me")
    assert header.co_simulation == CoSimulation(model_identifier="cs")
    cs = header.co_simulation
    assert cs is not None
    assert cs.max_output_derivative_order == 0
    assert not cs.can_handle_variable_communication_step_size
    unit = header.unit_definitions[0]
    assert unit.base_unit == BaseUnit(kg=0, m=0, s=0, A=0, K=0, mol=0, cd=0, rad=0, factor=1.0, offset=0.0)
    assert unit.display_units == (DisplayUnit(name="d", factor=1.0, offset=0.0),)
    real = header.type_definitions[0]
    assert isinstance(real, RealType)
    assert (real.relative_quantity, real.unbounded) == (False, False)


def test_missing_sections_are_empty_or_none() -> None:
    header = read_header(header_xml(""))
    assert header.model_exchange is None
    assert header.co_simulation is None
    assert header.unit_definitions == ()
    assert header.type_definitions == ()
    assert header.log_categories == ()
    assert header.default_experiment is None


def test_special_doubles() -> None:
    header = read_header(header_xml('<DefaultExperiment startTime="-INF" stopTime="INF" tolerance="NaN"/>'))
    experiment = header.default_experiment
    assert experiment is not None
    assert experiment.start_time == -math.inf
    assert experiment.stop_time == math.inf
    assert experiment.tolerance is not None
    assert math.isnan(experiment.tolerance)


def test_xsd_booleans_one_and_zero_are_valid_in_both_modes() -> None:
    xml = header_xml('<CoSimulation modelIdentifier="cs" canInterpolateInputs="1" needsExecutionTool="0"/>')
    for strict in (False, True):
        cs = read_header(xml, strict=strict).co_simulation
        assert cs is not None
        assert (cs.can_interpolate_inputs, cs.needs_execution_tool) == (True, False)


def test_vendor_annotations_are_skipped() -> None:
    xml = header_xml("<VendorAnnotations><Tool name='t'><Whatever x='1'><Deep/></Whatever></Tool></VendorAnnotations>")
    assert read_header(xml, strict=True).model_name == "M"


# --- Lenient vs strict ----------------------------------------------------------------------

LENIENT_FIXTURES = {
    "unknown attribute": (header_xml('<LogCategories><Category name="c" color="red"/></LogCategories>'), "color"),
    "unknown element": (header_xml("<Extensions><Something/></Extensions>"), "<Extensions>"),
    "unknown nested element": (
        header_xml('<CoSimulation modelIdentifier="cs"><Extra/></CoSimulation>'),
        "<Extra>",
    ),
    "boolean in other case": (
        header_xml('<CoSimulation modelIdentifier="cs" canInterpolateInputs="True"/>'),
        "canInterpolateInputs",
    ),
    "unknown enum value": (
        header_xml("", 'modelName="M" guid="g" variableNamingConvention="dotted"'),
        "variableNamingConvention",
    ),
    "invalid optional number": (header_xml('<DefaultExperiment stopTime="ten"/>'), "stopTime"),
    "missing required attribute": (header_xml("<UnitDefinitions><Unit/></UnitDefinitions>"), "'name'"),
    "missing required root attribute": (header_xml("", 'modelName="M"'), "'guid'"),
    "two DefaultExperiments": (
        header_xml('<DefaultExperiment stopTime="1"/><DefaultExperiment stopTime="2"/>'),
        "DefaultExperiment",
    ),
    "two type kinds": (
        header_xml('<TypeDefinitions><SimpleType name="t"><Real/><Integer/></SimpleType></TypeDefinitions>'),
        "type elements",
    ),
}


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_lenient_fixture_parses(case: str) -> None:
    xml, _ = LENIENT_FIXTURES[case]
    assert read_header(xml).model_name == "M"


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_same_fixture_raises_in_strict_mode(case: str) -> None:
    xml, message = LENIENT_FIXTURES[case]
    with pytest.raises(ParseError, match=message.replace("(", r"\(")):
        read_header(xml, strict=True)


def test_lenient_values() -> None:
    header = read_header(
        header_xml(
            '<CoSimulation modelIdentifier="cs" canInterpolateInputs="True" color="red"><Extra/></CoSimulation>'
            "<UnitDefinitions><Unit/></UnitDefinitions>"
            '<DefaultExperiment stopTime="ten" startTime="1"/><DefaultExperiment stopTime="2"/>'
            '<TypeDefinitions><SimpleType name="t"><Integer min="1"/><Real/></SimpleType></TypeDefinitions>',
            'modelName="M" variableNamingConvention="dotted"',
        )
    )
    assert header.guid == ""  # missing required text becomes ""
    assert header.variable_naming_convention == "dotted"
    assert header.co_simulation == CoSimulation(model_identifier="cs", can_interpolate_inputs=True)
    assert header.unit_definitions == (Unit(name=""),)
    assert header.default_experiment == DefaultExperiment(start_time=1.0)  # first one wins; bad stopTime dropped
    assert header.type_definitions == (IntegerType(name="t", min=1),)  # first type kind wins


def test_strict_mode_requires_model_variables() -> None:
    xml = b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g"/>'
    assert read_header(xml).model_name == "M"
    with pytest.raises(ParseError, match="no <ModelVariables>"):
        read_header(xml, strict=True)


# --- Errors in both modes -------------------------------------------------------------------


@pytest.mark.parametrize("strict", [False, True])
def test_missing_required_non_text_attribute_raises_in_both_modes(strict: bool) -> None:
    xml = header_xml(
        '<TypeDefinitions><SimpleType name="e"><Enumeration><Item name="a"/></Enumeration>'
        "</SimpleType></TypeDefinitions>"
    )
    with pytest.raises(ParseError, match="'value'"):
        read_header(xml, strict=strict)


@pytest.mark.parametrize("strict", [False, True])
def test_invalid_required_value_raises_in_both_modes(strict: bool) -> None:
    xml = header_xml(
        '<TypeDefinitions><SimpleType name="e"><Enumeration><Item name="a" value="one"/>'
        "</Enumeration></SimpleType></TypeDefinitions>"
    )
    with pytest.raises(ParseError, match="value='one'"):
        read_header(xml, strict=strict)


@pytest.mark.parametrize("strict", [False, True])
def test_simple_type_without_a_kind_raises_in_both_modes(strict: bool) -> None:
    with pytest.raises(ParseError, match="no Real, Integer"):
        read_header(header_xml('<TypeDefinitions><SimpleType name="t"/></TypeDefinitions>'), strict=strict)


def test_errors_point_at_the_nested_element() -> None:
    xml = (
        b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g">\n'
        b"  <UnitDefinitions>\n"
        b'    <Unit name="u">\n'
        b'      <BaseUnit m="one"/>\n'
        b"    </Unit>\n"
        b"  </UnitDefinitions>\n"
        b"  <ModelVariables/>\n"
        b"</fmiModelDescription>"
    )
    with pytest.raises(ParseError) as info:
        read_header(xml, strict=True)
    assert (info.value.line, info.value.column) == (4, 7)
    assert "<BaseUnit>" in str(info.value)


def test_to_dict_writes_special_doubles_as_xsd_strings() -> None:
    import json

    from mdxml import to_dict

    header = read_header(header_xml('<DefaultExperiment startTime="-INF" stopTime="INF" tolerance="NaN"/>'))
    data = to_dict(header)
    assert data["default_experiment"] == {"start_time": "-INF", "stop_time": "INF", "tolerance": "NaN"}
    json.dumps(data, allow_nan=False)  # strict JSON: raises if any inf/nan float slipped through


def test_cli_strict_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "md.xml"
    path.write_bytes(header_xml('<LogCategories><Category name="c" color="red"/></LogCategories>'))

    assert mdxml.main(["header", str(path)]) == 0
    capsys.readouterr()
    assert mdxml.main(["header", str(path), "--strict"]) == 1
    assert "unknown attribute 'color'" in capsys.readouterr().err


# --- Still stops at <ModelVariables> --------------------------------------------------------


def test_full_header_never_reads_past_model_variables() -> None:
    data = FULL.read_bytes()
    cut = data.index(b"<ModelVariables>") + len(b"<ModelVariables>")
    broken = data[:cut] + b"<<< not xml &&& </nope>"
    assert read_header(broken, strict=True) == read_header(FULL)
