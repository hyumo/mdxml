"""Issue #8: iter_variables for FMI 3."""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import mdxml
from mdxml import ParseError, Source, fmi3, iter_variables, to_dict
from mdxml.fmi3 import (
    Alias,
    BinaryVariable,
    BooleanVariable,
    Causality,
    ClockVariable,
    Dimension,
    EnumerationVariable,
    Float32Variable,
    Float64Variable,
    Initial,
    Int8Variable,
    Int32Variable,
    IntervalVariability,
    StringVariable,
    UInt64Variable,
    Variability,
    default_variability,
)

DATA = Path(__file__).parent / "data"
REFERENCE_FMI3 = sorted((DATA / "reference_fmus").glob("*/FMI3.xml"))
VARIABLES = DATA / "fmi3" / "variables.xml"


def fmi3_variables(src: Source, **options: Any) -> list[fmi3.Variable]:
    """Collect every variable, checking each is an FMI 3 one."""
    out: list[fmi3.Variable] = []
    for variable in iter_variables(src, **options):
        assert isinstance(variable, fmi3.AbstractVariable)
        out.append(variable)
    return out


def model(variables: str) -> bytes:
    return (
        '<fmiModelDescription fmiVersion="3.0" modelName="M" instantiationToken="t">'
        f"<ModelVariables>{variables}</ModelVariables><ModelStructure/></fmiModelDescription>"
    ).encode()


# --- Every reference variable, checked against an independent ElementTree reading ----------


def _xs_bool(text: str) -> bool:
    return text in {"true", "1"}


_ITEM: dict[str, Callable[[str], object]] = {
    **dict.fromkeys(("Float32", "Float64"), float),
    **dict.fromkeys(("Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Enumeration"), int),
    "Boolean": _xs_bool,
    "String": str,
    "Binary": bytes.fromhex,
}


def _spec_variability(tag: str, causality: str) -> str:
    # Written independently of the library, from the FMI 3.0.2 text on `variability`.
    if causality in {"parameter", "structuralParameter", "calculatedParameter"}:
        return "fixed"
    return "continuous" if tag in {"Float32", "Float64"} else "discrete"


def expected_from_elementtree(path: Path) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    model_variables = root.find("ModelVariables")
    assert model_variables is not None
    expected: list[dict[str, Any]] = []
    for index, element in enumerate(model_variables, start=1):
        tag = element.tag
        causality = element.get("causality", "local")
        dimensions = [(d.get("start"), d.get("valueReference")) for d in element.findall("Dimension")]
        if tag in {"String", "Binary"}:
            raw = [s.get("value", "") for s in element.findall("Start")]
        else:
            raw = element.get("start", "").split()
        values = tuple(_ITEM[tag](v) for v in raw) if tag != "Clock" else ()
        start: object = values if dimensions else (values[0] if values else None)
        clocks = element.get("clocks")
        expected.append(
            {
                "index": index,
                "type_name": tag,
                "name": element.get("name"),
                "value_reference": int(element.get("valueReference", "-1")),
                "causality": causality,
                "variability": element.get("variability", _spec_variability(tag, causality)),
                "initial": element.get("initial"),
                "declared_type": element.get("declaredType"),
                "start": start,
                "dimensions": [(None if s is None else int(s), None if v is None else int(v)) for s, v in dimensions],
                "clocks": None if clocks is None else tuple(int(c) for c in clocks.split()),
            }
        )
    return expected


def actual(variable: fmi3.Variable) -> dict[str, Any]:
    values: dict[str, Any] = {
        "index": variable.index,
        "type_name": variable.type_name,
        "name": variable.name,
        "value_reference": variable.value_reference,
        "causality": variable.causality,
        "variability": variable.variability,
        "initial": None,
        "declared_type": variable.declared_type,
        "start": None,
        "dimensions": [],
        "clocks": variable.clocks,
    }
    if not isinstance(variable, ClockVariable):
        values["initial"] = variable.initial
        values["start"] = variable.start
        values["dimensions"] = [(d.start, d.value_reference) for d in variable.dimensions]
    return values


@pytest.mark.parametrize("path", REFERENCE_FMI3, ids=lambda p: p.parent.name)
def test_every_reference_variable_matches_an_independent_reading(path: Path) -> None:
    variables = fmi3_variables(path, strict=True)
    assert [actual(v) for v in variables] == expected_from_elementtree(path)


def test_feedthrough_has_every_type_kind() -> None:
    variables = fmi3_variables(DATA / "reference_fmus" / "Feedthrough" / "FMI3.xml")
    kinds = {v.type_name for v in variables}
    assert kinds == {
        "Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32",
        "Int64", "UInt64", "Boolean", "String", "Binary", "Enumeration",
    }  # fmt: skip
    binary = next(v for v in variables if isinstance(v, BinaryVariable) and v.start is not None)
    assert binary.start == b"foo"


def test_state_space_arrays_refer_to_structural_parameters() -> None:
    variables = {v.name: v for v in fmi3_variables(DATA / "reference_fmus" / "StateSpace" / "FMI3.xml")}
    m = variables["m"]
    a = variables["A"]
    assert isinstance(m, UInt64Variable)
    assert m.causality is Causality.STRUCTURAL_PARAMETER
    assert isinstance(a, Float64Variable)
    assert a.is_array
    assert a.start == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    n = variables["n"]
    assert m.value_reference != n.value_reference
    # A is the n x n state matrix: both dimensions are sized by the structural parameter n.
    assert [d.value_reference for d in a.dimensions] == [n.value_reference, n.value_reference]


def test_clocks_reference_file() -> None:
    variables = fmi3_variables(DATA / "reference_fmus" / "Clocks" / "FMI3.xml")
    clocks = [v for v in variables if isinstance(v, ClockVariable)]
    assert [c.interval_variability for c in clocks] == [
        IntervalVariability.CONSTANT,
        IntervalVariability.TRIGGERED,
        IntervalVariability.COUNTDOWN,
        IntervalVariability.TRIGGERED,
    ]
    assert all(c.variability is Variability.DISCRETE for c in clocks)


# --- All kinds and attributes ---------------------------------------------------------------


def by_name() -> dict[str, fmi3.Variable]:
    return {v.name: v for v in fmi3_variables(VARIABLES, strict=True)}


def test_float_with_every_attribute_and_aliases() -> None:
    assert by_name()["f64"] == Float64Variable(
        name="f64",
        value_reference=1,
        index=1,
        description="a double",
        causality=Causality.OUTPUT,
        variability=Variability.DISCRETE,
        initial=Initial.EXACT,
        can_handle_multiple_set_per_time_instant=False,
        clocks=(10, 11),
        declared_type="T",
        intermediate_update=True,
        previous=2,
        quantity="Q",
        unit="m",
        display_unit="mm",
        relative_quantity=True,
        unbounded=True,
        min=-1.0,
        max=math.inf,
        nominal=2.0,
        start=0.5,
        derivative=3,
        reinit=True,
        aliases=(Alias(name="f64_alias", description="another name", display_unit="km"), Alias(name="f64_alias2")),
    )


def test_arrays_have_tuple_starts_and_dimensions() -> None:
    variables = by_name()
    assert variables["f32_array"] == Float32Variable(
        name="f32_array",
        value_reference=2,
        index=2,
        causality=Causality.PARAMETER,
        variability=Variability.TUNABLE,
        start=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
        dimensions=(Dimension(start=2), Dimension(value_reference=100)),
    )
    assert variables["i32_array"] == Int32Variable(
        name="i32_array",
        value_reference=7,
        index=7,
        causality=Causality.STRUCTURAL_PARAMETER,
        variability=Variability.FIXED,
        start=(1, 2),
        dimensions=(Dimension(start=2),),
    )
    b_array = variables["b_array"]
    assert isinstance(b_array, BooleanVariable)
    assert b_array.start == (True, False, True, False)
    s_array = variables["s_array"]
    assert isinstance(s_array, StringVariable)
    assert s_array.start == ("a", "b")


def test_integer_extremes() -> None:
    variables = by_name()
    starts = {name: getattr(variables[name], "start", None) for name in ("i8", "u8", "i16", "u16", "u32", "i64", "u64")}
    assert starts == {
        "i8": -5,
        "u8": 255,
        "i16": -32768,
        "u16": 65535,
        "u32": 2**32 - 1,
        "i64": -(2**63),
        "u64": 2**64 - 1,
    }
    i8 = variables["i8"]
    assert isinstance(i8, Int8Variable)
    assert (i8.quantity, i8.min, i8.max) == ("Count", -128, 127)


def test_string_and_binary_start_children() -> None:
    variables = by_name()
    assert variables["s"] == StringVariable(
        name="s",
        value_reference=12,
        index=12,
        causality=Causality.PARAMETER,
        variability=Variability.FIXED,
        start="hello world",
        aliases=(Alias(name="s_alias"),),
    )
    assert variables["bin"] == BinaryVariable(
        name="bin",
        value_reference=14,
        index=14,
        causality=Causality.INPUT,
        variability=Variability.DISCRETE,
        mime_type="image/png",
        max_size=16,
        start=bytes.fromhex("cafebabe"),
    )


def test_enumeration_and_clock() -> None:
    variables = by_name()
    assert variables["e"] == EnumerationVariable(
        name="e",
        value_reference=15,
        index=15,
        variability=Variability.DISCRETE,
        declared_type="Mode",
        quantity="Mode",
        min=0,
        max=1,
        start=1,
    )
    assert variables["clk"] == ClockVariable(
        name="clk",
        value_reference=16,
        index=16,
        description="a clock",
        causality=Causality.INPUT,
        variability=Variability.DISCRETE,
        declared_type="C",
        can_be_deactivated=True,
        priority=2,
        interval_variability=IntervalVariability.COUNTDOWN,
        interval_decimal=0.1,
        shift_decimal=0.05,
        supports_fraction=True,
        resolution=1000,
        interval_counter=100,
        shift_counter=50,
        aliases=(Alias(name="clk_alias"),),
    )


def test_defaults() -> None:
    defaults = by_name()["defaults"]
    assert defaults == Float64Variable(
        name="defaults", value_reference=17, index=17, variability=Variability.CONTINUOUS
    )
    assert isinstance(defaults, Float64Variable)
    assert defaults.causality is Causality.LOCAL
    assert (defaults.dimensions, defaults.aliases, defaults.start) == ((), (), None)
    assert not defaults.is_array
    assert defaults.effective_initial is Initial.CALCULATED


def test_type_names_and_indexes() -> None:
    variables = fmi3_variables(VARIABLES)
    assert [v.index for v in variables] == list(range(1, 18))
    assert [v.type_name for v in variables][:3] == ["Float64", "Float32", "Int8"]


# --- Defaults from the standard -------------------------------------------------------------

SPEC_TABLE_22 = """
             structuralParameter  parameter  calculatedParameter  input  output      local       independent
constant     -                    -          -                    -      exact       exact       -
fixed        exact                exact      calculated           -      -           calculated  -
tunable      exact                exact      calculated           -      -           calculated  -
discrete     -                    -          -                    exact  calculated  calculated  -
continuous   -                    -          -                    exact  calculated  calculated  -
"""


def _table_22() -> Iterator[tuple[str, str, str]]:
    header, *rows = SPEC_TABLE_22.strip().splitlines()
    causalities = header.split()
    for row in rows:
        variability, *cells = row.split()
        for causality, cell in zip(causalities, cells, strict=True):
            yield causality, variability, cell


@pytest.mark.parametrize(("causality", "variability", "cell"), list(_table_22()))
def test_effective_initial_follows_table_22(causality: str, variability: str, cell: str) -> None:
    xml = model(f'<Float64 name="v" valueReference="1" causality="{causality}" variability="{variability}"/>')
    (variable,) = fmi3_variables(xml)
    assert isinstance(variable, Float64Variable)
    assert variable.initial is None
    assert variable.effective_initial == (None if cell == "-" else Initial(cell))


@pytest.mark.parametrize(
    ("element", "causality", "expected"),
    [
        ("Float64", "local", Variability.CONTINUOUS),
        ("Float32", "output", Variability.CONTINUOUS),
        ("Float64", "independent", Variability.CONTINUOUS),
        ("Float64", "parameter", Variability.FIXED),
        ("Int32", "structuralParameter", Variability.FIXED),
        ("Boolean", "calculatedParameter", Variability.FIXED),
        ("Int32", "output", Variability.DISCRETE),
        ("String", "input", Variability.DISCRETE),
        ("Clock", "input", Variability.DISCRETE),
    ],
)
def test_default_variability(element: str, causality: str, expected: Variability) -> None:
    assert default_variability(element, causality) is expected
    extra = ' intervalVariability="triggered"' if element == "Clock" else ""
    (variable,) = fmi3_variables(model(f'<{element} name="v" valueReference="1" causality="{causality}"{extra}/>'))
    assert variable.variability is expected


# --- Filters --------------------------------------------------------------------------------

FILTER_MODEL = model(
    '<Float64 name="plant.x" valueReference="1" causality="output"/>'
    '<Int32 name="plant.n" valueReference="2" causality="output"/>'  # default variability: discrete
    '<UInt64 name="size" valueReference="3" causality="structuralParameter"/>'  # default: fixed
    '<Float64 name="ctrl.u" valueReference="4" causality="input"/>'  # default: continuous
    '<Clock name="ctrl.clk" valueReference="5" causality="input" intervalVariability="triggered"/>'
)


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"causality": "output"}, [("plant.x", 1), ("plant.n", 2)]),
        ({"causality": Causality.STRUCTURAL_PARAMETER}, [("size", 3)]),
        ({"variability": "continuous"}, [("plant.x", 1), ("ctrl.u", 4)]),
        ({"variability": "discrete"}, [("plant.n", 2), ("ctrl.clk", 5)]),
        ({"variability": Variability.FIXED}, [("size", 3)]),
        ({"name_prefix": "ctrl."}, [("ctrl.u", 4), ("ctrl.clk", 5)]),
        ({"causality": "input", "variability": "discrete"}, [("ctrl.clk", 5)]),
    ],
)
def test_filters_use_the_fmi3_defaults(options: dict[str, Any], expected: list[tuple[str, int]]) -> None:
    assert [(v.name, v.index) for v in fmi3_variables(FILTER_MODEL, **options)] == expected


def test_skipped_variables_are_never_built(monkeypatch: pytest.MonkeyPatch) -> None:
    from mdxml._schema import AttrTable, Frame, attributes
    from mdxml.fmi3._variables import VARIABLE_GRAMMARS

    built: list[str] = []

    def counting(frame: Frame, spec: AttrTable, *, strict: bool) -> dict[str, Any]:
        if frame.tag in VARIABLE_GRAMMARS:
            built.append(frame.attrs["name"])
        return attributes(frame, spec, strict=strict)

    monkeypatch.setattr("mdxml.fmi3._variables.attributes", counting)
    assert [v.name for v in fmi3_variables(FILTER_MODEL, causality="input")] == ["ctrl.u", "ctrl.clk"]
    assert built == ["ctrl.u", "ctrl.clk"]


# --- .header from the same pass -------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCE_FMI3, ids=lambda p: p.parent.name)
def test_header_equals_read_header(path: Path) -> None:
    variables = iter_variables(path)
    assert next(variables).index == 1
    assert variables.header == mdxml.read_header(path)


def test_header_before_iterating() -> None:
    variables = iter_variables(VARIABLES)
    header = variables.header
    assert isinstance(header, fmi3.ModelHeader)
    assert header.model_name == "Vars3"
    assert len(list(variables)) == 17


# --- Lenient vs strict ----------------------------------------------------------------------

LENIENT_FIXTURES = {
    "scalar with several start values": (model('<Float64 name="v" valueReference="1" start="1 2"/>'), "start values"),
    "unknown variable element": (
        model('<Float128 name="x" valueReference="9"/><Float64 name="v" valueReference="1"/>'),
        "<Float128>",
    ),
    "unknown attribute": (model('<Int8 name="v" valueReference="1" color="red"/>'), "color"),
    "out-of-range start item": (model('<Int8 name="v" valueReference="1" start="300"/>'), "xs:byte"),
    "bad hex in Binary start": (
        model('<Binary name="v" valueReference="1"><Start value="zz"/></Binary>'),
        "hex|value",
    ),
    "Dimension on a Clock": (
        model('<Clock name="v" valueReference="1" intervalVariability="triggered"><Dimension start="2"/></Clock>'),
        "<Dimension>",
    ),
    "displayUnit on a non-float alias": (
        model('<Int32 name="v" valueReference="1"><Alias name="a" displayUnit="mm"/></Int32>'),
        "displayUnit",
    ),
    "unknown causality": (model('<Float64 name="v" valueReference="1" causality="weird"/>'), "causality"),
    "missing Enumeration declaredType": (model('<Enumeration name="v" valueReference="1"/>'), "declaredType"),
}


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_lenient_fixture_yields_the_variable(case: str) -> None:
    xml, _ = LENIENT_FIXTURES[case]
    assert [v.name for v in fmi3_variables(xml)] == ["v"]


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_same_fixture_raises_in_strict_mode(case: str) -> None:
    xml, message = LENIENT_FIXTURES[case]
    with pytest.raises(ParseError, match=message):
        list(iter_variables(xml, strict=True))


def test_lenient_values() -> None:
    (several,) = fmi3_variables(model('<Float64 name="v" valueReference="1" start="1 2"/>'))
    assert isinstance(several, Float64Variable)
    assert several.start == (1.0, 2.0)  # kept as written rather than dropped
    (out_of_range,) = fmi3_variables(model('<Int8 name="v" valueReference="1" start="300"/>'))
    assert isinstance(out_of_range, Int8Variable)
    assert out_of_range.start is None


@pytest.mark.parametrize("strict", [False, True])
def test_clock_without_interval_variability_raises_in_both_modes(strict: bool) -> None:
    with pytest.raises(ParseError, match="intervalVariability"):
        list(iter_variables(model('<Clock name="c" valueReference="1"/>'), strict=strict))


def test_single_element_array_keeps_a_tuple() -> None:
    (variable,) = fmi3_variables(
        model('<Float64 name="v" valueReference="1" start="7"><Dimension start="1"/></Float64>')
    )
    assert isinstance(variable, Float64Variable)
    assert variable.start == (7.0,)


# --- Output ---------------------------------------------------------------------------------


def test_to_dict_turns_bytes_into_hex_and_is_strict_json() -> None:
    variables = by_name()
    binary = to_dict(variables["bin"])
    assert binary["start"] == "cafebabe"
    array = to_dict(variables["f32_array"])
    assert array["start"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert array["dimensions"] == [{"start": 2}, {"value_reference": 100}]
    for variable in variables.values():
        json.dumps(to_dict(variable), allow_nan=False)


def test_cli_variables_on_fmi3(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "md.xml"
    path.write_bytes(FILTER_MODEL)
    assert mdxml.main(["variables", str(path), "--variability", "fixed"]) == 0
    (line,) = capsys.readouterr().out.splitlines()
    assert json.loads(line) == {
        "name": "size",
        "value_reference": 3,
        "index": 3,
        "variability": "fixed",
        "causality": "structuralParameter",
        "aliases": [],
        "dimensions": [],
        "type_name": "UInt64",
    }
