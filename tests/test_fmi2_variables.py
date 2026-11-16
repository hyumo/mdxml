"""Issue #7: iter_variables for FMI 2."""

from __future__ import annotations

import io
import json
import math
import tracemalloc
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, Any, cast

import pytest

import mdxml
from mdxml import ParseError, Source, fmi2, iter_variables, to_dict
from mdxml.fmi2 import (
    BooleanVariable,
    Causality,
    EnumerationVariable,
    Initial,
    IntegerVariable,
    RealVariable,
    StringVariable,
    Variability,
)

DATA = Path(__file__).parent / "data"
REFERENCE_FMI2 = sorted((DATA / "reference_fmus").glob("*/FMI2.xml"))
VARIABLES = DATA / "fmi2" / "variables.xml"


def fmi2_variables(src: Source, **options: Any) -> list[fmi2.Variable]:
    """Collect every variable, checking each is an FMI 2 one."""
    out: list[fmi2.Variable] = []
    for variable in iter_variables(src, **options):
        assert isinstance(variable, fmi2.ScalarVariable)
        out.append(variable)
    return out


def model(variables: str, root_attrs: str = 'modelName="M" guid="g"') -> bytes:
    return (
        f'<fmiModelDescription fmiVersion="2.0" {root_attrs}><ModelVariables>{variables}</ModelVariables>'
        "<ModelStructure/></fmiModelDescription>"
    ).encode()


def scalar(name: str, vr: int, attrs: str = "", child: str = "<Real/>") -> str:
    return f'<ScalarVariable name="{name}" valueReference="{vr}" {attrs}>{child}</ScalarVariable>'


# --- Every reference variable, checked against an independent ElementTree reading ----------


def _xs_bool(text: str) -> bool:
    return text.strip() in {"true", "1"}


_CONVERT_START: dict[str, Callable[[str], object]] = {
    "Real": float,
    "Integer": int,
    "Enumeration": int,
    "Boolean": _xs_bool,
    "String": str,
}


def expected_from_elementtree(path: Path) -> list[dict[str, Any]]:
    root = ET.parse(path).getroot()
    model_variables = root.find("ModelVariables")
    assert model_variables is not None
    expected: list[dict[str, Any]] = []
    for index, element in enumerate(model_variables.findall("ScalarVariable"), start=1):
        (typed,) = [child for child in element if child.tag in _CONVERT_START]
        start = typed.get("start")
        expected.append(
            {
                "index": index,
                "type_name": typed.tag,
                "name": element.get("name"),
                "value_reference": int(element.get("valueReference", "-1")),
                "description": element.get("description"),
                "causality": element.get("causality", "local"),
                "variability": element.get("variability", "continuous"),
                "initial": element.get("initial"),
                "declared_type": typed.get("declaredType"),
                "start": None if start is None else _CONVERT_START[typed.tag](start),
            }
        )
    return expected


def actual(variable: fmi2.Variable) -> dict[str, Any]:
    return {
        "index": variable.index,
        "type_name": variable.type_name,
        "name": variable.name,
        "value_reference": variable.value_reference,
        "description": variable.description,
        "causality": variable.causality,
        "variability": variable.variability,
        "initial": variable.initial,
        "declared_type": variable.declared_type,
        "start": variable.start,
    }


@pytest.mark.parametrize("path", REFERENCE_FMI2, ids=lambda p: p.parent.name)
def test_every_reference_variable_matches_an_independent_reading(path: Path) -> None:
    variables = fmi2_variables(path, strict=True)
    assert [actual(v) for v in variables] == expected_from_elementtree(path)


def test_bouncing_ball_variables() -> None:
    variables = fmi2_variables(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")
    assert [(v.index, v.name, v.causality, v.variability) for v in variables[:3]] == [
        (1, "time", Causality.INDEPENDENT, Variability.CONTINUOUS),
        (2, "h", Causality.OUTPUT, Variability.CONTINUOUS),
        (3, "der(h)", Causality.LOCAL, Variability.CONTINUOUS),
    ]
    der_h = variables[2]
    assert isinstance(der_h, RealVariable)
    assert der_h.derivative == 2  # the Variable Index of h


def test_all_kinds_and_attributes() -> None:
    r, i, b, s, e, defaults = fmi2_variables(VARIABLES, strict=True)
    assert r == RealVariable(
        name="r",
        value_reference=1,
        index=1,
        description="a real",
        causality=Causality.OUTPUT,
        variability=Variability.DISCRETE,
        initial=Initial.EXACT,
        can_handle_multiple_set_per_time_instant=True,
        declared_type="T",
        quantity="Q",
        unit="m",
        display_unit="mm",
        relative_quantity=True,
        min=-1.0,
        max=math.inf,
        nominal=2.0,
        unbounded=True,
        start=0.5,
        derivative=3,
        reinit=True,
    )
    assert i == IntegerVariable(
        name="i",
        value_reference=2,
        index=2,
        causality=Causality.PARAMETER,
        variability=Variability.FIXED,
        declared_type="I",
        quantity="Count",
        min=-5,
        max=5,
        start=3,
    )
    assert b == BooleanVariable(
        name="b",
        value_reference=3,
        index=3,
        causality=Causality.INPUT,
        variability=Variability.DISCRETE,
        declared_type="B",
        start=True,
    )
    assert s == StringVariable(
        name="s",
        value_reference=4,
        index=4,
        causality=Causality.PARAMETER,
        variability=Variability.TUNABLE,
        initial=Initial.EXACT,
        declared_type="S",
        start="hello",
    )
    assert e == EnumerationVariable(
        name="e",
        value_reference=5,
        index=5,
        causality=Causality.CALCULATED_PARAMETER,
        variability=Variability.FIXED,
        initial=Initial.APPROX,
        declared_type="Mode",
        quantity="Mode",
        min=0,
        max=1,
        start=1,
    )
    assert defaults == RealVariable(name="defaults", value_reference=6, index=6)
    assert isinstance(defaults, RealVariable)
    assert (defaults.causality, defaults.variability) == (Causality.LOCAL, Variability.CONTINUOUS)
    assert (defaults.relative_quantity, defaults.unbounded, defaults.reinit) == (False, False, False)
    assert [v.type_name for v in (r, i, b, s, e)] == ["Real", "Integer", "Boolean", "String", "Enumeration"]


def test_variables_are_frozen_with_slots() -> None:
    variable = fmi2_variables(VARIABLES)[0]
    assert not hasattr(variable, "__dict__")
    with pytest.raises(AttributeError):
        variable.name = "x"  # type: ignore[misc]


# --- effective_initial: the FMI 2 standard's causality x variability table ------------------

# Rows: variability. Columns: causality. Cell: default initial, "-" for "no initial", "x" for invalid.
SPEC_TABLE = """
             parameter  calculatedParameter  input  output      local       independent
constant     x          x                    x      exact       exact       x
fixed        exact      calculated           x      x           calculated  x
tunable      exact      calculated           x      x           calculated  x
discrete     x          x                    -      calculated  calculated  x
continuous   x          x                    -      calculated  calculated  -
"""


def _spec_cases() -> Iterator[tuple[str, str, str]]:
    header, *rows = SPEC_TABLE.strip().splitlines()
    causalities = header.split()
    for row in rows:
        variability, *cells = row.split()
        for causality, cell in zip(causalities, cells, strict=True):
            yield causality, variability, cell


@pytest.mark.parametrize(("causality", "variability", "cell"), list(_spec_cases()))
def test_effective_initial_follows_the_spec_table(causality: str, variability: str, cell: str) -> None:
    (variable,) = fmi2_variables(model(scalar("v", 1, f'causality="{causality}" variability="{variability}"')))
    expected = None if cell in {"-", "x"} else Initial(cell)
    assert variable.initial is None
    assert variable.effective_initial == expected


def test_effective_initial_keeps_a_written_initial() -> None:
    (variable,) = fmi2_variables(model(scalar("v", 1, 'causality="output" initial="exact"')))
    assert variable.effective_initial is Initial.EXACT


def test_effective_initial_of_unknown_values_is_none() -> None:
    (variable,) = fmi2_variables(model(scalar("v", 1, 'causality="weird"')))
    assert variable.causality == "weird"
    assert variable.effective_initial is None


# --- Filters --------------------------------------------------------------------------------

FILTER_MODEL = model(
    scalar("plant.x", 1, 'causality="output"')
    + scalar("plant.y", 2)  # causality defaults to local
    + scalar("ctrl.u", 3, 'causality="input" variability="discrete"')
    + scalar("ctrl.k", 4, 'causality="parameter" variability="fixed"')
    + scalar("plant.z", 5, 'causality="output" variability="discrete"')
)


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"causality": "output"}, [("plant.x", 1), ("plant.z", 5)]),
        ({"causality": Causality.OUTPUT}, [("plant.x", 1), ("plant.z", 5)]),
        ({"causality": ["input", Causality.PARAMETER]}, [("ctrl.u", 3), ("ctrl.k", 4)]),
        ({"causality": "local"}, [("plant.y", 2)]),
        ({"variability": "discrete"}, [("ctrl.u", 3), ("plant.z", 5)]),
        ({"variability": Variability.CONTINUOUS}, [("plant.x", 1), ("plant.y", 2)]),
        ({"name_prefix": "plant."}, [("plant.x", 1), ("plant.y", 2), ("plant.z", 5)]),
        ({"name_prefix": "plant.", "causality": "output", "variability": "discrete"}, [("plant.z", 5)]),
        ({"causality": []}, []),
    ],
)
def test_filters_keep_exactly_the_matching_variables_with_their_index(
    options: dict[str, Any], expected: list[tuple[str, int]]
) -> None:
    assert [(v.name, v.index) for v in fmi2_variables(FILTER_MODEL, **options)] == expected


def test_skipped_variables_are_never_built(monkeypatch: pytest.MonkeyPatch) -> None:
    from mdxml._schema import AttrTable, Frame, attributes
    from mdxml.fmi2._variables import SCALAR_VARIABLE_ATTRS

    built: list[str] = []

    def counting(frame: Frame, spec: AttrTable, *, strict: bool) -> dict[str, Any]:
        if spec is SCALAR_VARIABLE_ATTRS:
            built.append(frame.attrs["name"])
        return attributes(frame, spec, strict=strict)

    monkeypatch.setattr("mdxml.fmi2._variables.attributes", counting)

    assert [v.name for v in fmi2_variables(FILTER_MODEL, causality="output")] == ["plant.x", "plant.z"]
    assert built == ["plant.x", "plant.z"]


# --- .header from the same pass -------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCE_FMI2, ids=lambda p: p.parent.name)
def test_header_equals_read_header(path: Path) -> None:
    variables = iter_variables(path)
    first = next(variables)
    assert first.index == 1
    assert variables.header == mdxml.read_header(path)


def test_header_before_iterating_consumes_no_variables() -> None:
    variables = iter_variables(VARIABLES)
    assert variables.header.model_name == "Vars"
    assert [v.name for v in variables] == ["r", "i", "b", "s", "e", "defaults"]


class ForwardOnly(io.RawIOBase):
    def __init__(self, data: bytes) -> None:
        self._inner = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(size)


def test_header_and_variables_come_from_one_pass() -> None:
    # A stream that can't be rewound can only be read once: both must come from that read.
    variables = iter_variables(ForwardOnly(VARIABLES.read_bytes()))
    names = [v.name for v in variables]
    assert variables.header.model_name == "Vars"
    assert names == ["r", "i", "b", "s", "e", "defaults"]


def test_small_file_iterated_without_touching_header() -> None:
    # Regression: the chunk that finishes the document also queues every variable.
    assert len(fmi2_variables(DATA / "reference_fmus" / "BouncingBall" / "FMI2.xml")) == 8


def test_model_without_variables() -> None:
    variables = iter_variables(b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g"/>')
    assert list(variables) == []
    assert variables.header.model_name == "M"
    with pytest.raises(ParseError, match="no <ModelVariables>"):
        list(iter_variables(b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g"/>', strict=True))


# --- Streaming: flat memory, early stop, closing --------------------------------------------


def write_large_model(path: Path, count: int) -> Path:
    with path.open("w", encoding="utf-8") as out:
        out.write('<fmiModelDescription fmiVersion="2.0" modelName="Big" guid="g"><ModelVariables>')
        for i in range(count):
            out.write(
                f'<ScalarVariable name="v{i}" valueReference="{i}" causality="output">'
                f'<Real start="{i}.5" unit="m"/></ScalarVariable>'
            )
        out.write("</ModelVariables><ModelStructure/></fmiModelDescription>")
    return path


def peak_memory_while_iterating(path: Path) -> tuple[int, int]:
    tracemalloc.start()
    try:
        count = sum(1 for _ in iter_variables(path))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return count, peak


def test_peak_memory_does_not_grow_with_variable_count(tmp_path: Path) -> None:
    small_count, small_peak = peak_memory_while_iterating(write_large_model(tmp_path / "small.xml", 2_000))
    large_count, large_peak = peak_memory_while_iterating(write_large_model(tmp_path / "large.xml", 40_000))

    assert (small_count, large_count) == (2_000, 40_000)
    assert (tmp_path / "large.xml").stat().st_size > 3_000_000
    # 20x the variables; peak memory must stay about the same (bounded by one chunk's worth).
    assert large_peak < small_peak * 1.5 + 256 * 1024


def test_nothing_after_model_variables_is_read() -> None:
    data = VARIABLES.read_bytes()
    cut = data.index(b"</ModelVariables>") + len(b"</ModelVariables>")
    broken = data[:cut] + b"<<< not xml &&& </nope>"
    assert [v.name for v in fmi2_variables(broken, strict=True)] == ["r", "i", "b", "s", "e", "defaults"]


def test_closing_early_closes_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    opened: list[IO[bytes]] = []
    original_open = builtins.open

    def recording_open(*args: Any, **kwargs: Any) -> Any:
        file = cast("IO[bytes]", original_open(*args, **kwargs))
        opened.append(file)
        return file

    path = write_large_model(tmp_path / "big.xml", 20_000)
    monkeypatch.setattr("mdxml._source.open", recording_open, raising=False)

    with iter_variables(path) as variables:
        assert next(variables).name == "v0"
        assert not opened[0].closed
    assert opened[0].closed


def test_exhausting_closes_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    opened: list[IO[bytes]] = []
    original_open = builtins.open

    def recording_open(*args: Any, **kwargs: Any) -> Any:
        file = cast("IO[bytes]", original_open(*args, **kwargs))
        opened.append(file)
        return file

    monkeypatch.setattr("mdxml._source.open", recording_open, raising=False)
    variables = iter_variables(VARIABLES)
    assert len(list(variables)) == 6
    assert opened[0].closed
    assert list(variables) == []  # exhausted iterators stay exhausted


def test_nothing_is_opened_until_used(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []

    def recording_open(*args: object, **kwargs: object) -> None:
        opened.append(str(args[0]))

    monkeypatch.setattr("mdxml._source.open", recording_open, raising=False)
    iter_variables(VARIABLES)
    assert opened == []


def test_missing_file_fails_at_call_time(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        iter_variables(tmp_path / "missing.fmu")


def test_works_on_zipped_fmus_and_respects_max_xml_bytes(tmp_path: Path) -> None:
    import zipfile

    fmu = tmp_path / "vars.fmu"
    with zipfile.ZipFile(fmu, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(VARIABLES, "modelDescription.xml")
    assert len(fmi2_variables(fmu)) == 6
    with pytest.raises(mdxml.UnsafeInput):
        list(iter_variables(fmu, max_xml_bytes=100))


# --- Lenient vs strict ----------------------------------------------------------------------

LENIENT_FIXTURES = {
    "unknown element in ModelVariables": (model("<Extra/>" + scalar("v", 1)), "<Extra>"),
    "unknown attribute on ScalarVariable": (model(scalar("v", 1, 'color="red"')), "color"),
    "unknown child of ScalarVariable": (model(scalar("v", 1, "", "<Real/><Extra/>")), "<Extra>"),
    "unknown attribute on Real": (model(scalar("v", 1, "", '<Real color="red"/>')), "color"),
    "unknown causality": (model(scalar("v", 1, 'causality="weird"')), "causality"),
    "boolean in other case": (model(scalar("v", 1, "", '<Real reinit="True"/>')), "reinit"),
    "two type elements": (model(scalar("v", 1, "", "<Real/><Integer/>")), "type elements"),
    "missing name": (model('<ScalarVariable valueReference="1"><Real/></ScalarVariable>'), "'name'"),
    "missing Enumeration declaredType": (model(scalar("v", 1, "", "<Enumeration/>")), "declaredType"),
}


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_lenient_fixture_yields_the_variable(case: str) -> None:
    xml, _ = LENIENT_FIXTURES[case]
    (variable,) = fmi2_variables(xml)
    assert variable.index == 1


@pytest.mark.parametrize("case", LENIENT_FIXTURES, ids=list(LENIENT_FIXTURES))
def test_same_fixture_raises_in_strict_mode(case: str) -> None:
    xml, message = LENIENT_FIXTURES[case]
    with pytest.raises(ParseError, match=message):
        list(iter_variables(xml, strict=True))


@pytest.mark.parametrize("strict", [False, True])
def test_variable_without_a_type_element_raises_in_both_modes(strict: bool) -> None:
    with pytest.raises(ParseError, match="has no Real"):
        list(iter_variables(model(scalar("v", 1, "", "")), strict=strict))


@pytest.mark.parametrize("strict", [False, True])
def test_missing_value_reference_raises_in_both_modes(strict: bool) -> None:
    with pytest.raises(ParseError, match="valueReference"):
        list(iter_variables(model('<ScalarVariable name="v"><Real/></ScalarVariable>'), strict=strict))


def test_errors_point_at_the_variable() -> None:
    xml = (
        b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g">\n'
        b"<ModelVariables>\n"
        b'  <ScalarVariable name="ok" valueReference="1"><Real/></ScalarVariable>\n'
        b'  <ScalarVariable name="bad" valueReference="2"><Real start="nope"/></ScalarVariable>\n'
        b"</ModelVariables></fmiModelDescription>"
    )
    variables = iter_variables(xml, strict=True)
    with pytest.raises(ParseError) as info:
        list(variables)
    assert info.value.line == 4


# --- Output ---------------------------------------------------------------------------------


def test_to_dict_of_a_variable_is_strict_json() -> None:
    r = fmi2_variables(VARIABLES)[0]
    data = to_dict(r)
    assert data["max"] == "INF"
    assert data["causality"] == "output"
    assert data["type_name"] == "Real"
    json.dumps(data, allow_nan=False)


@pytest.fixture
def filter_model_path(tmp_path: Path) -> Path:
    path = tmp_path / "filters.xml"
    path.write_bytes(FILTER_MODEL)
    return path


def test_cli_variables_prints_json_lines(filter_model_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mdxml.main(["variables", str(filter_model_path), "--causality", "output", "--causality", "input"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["name"] for line in lines] == ["plant.x", "ctrl.u", "plant.z"]


def test_cli_variables_name_prefix_and_errors(
    filter_model_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert mdxml.main(["variables", str(filter_model_path), "--name-prefix", "ctrl."]) == 0
    assert [json.loads(line)["name"] for line in capsys.readouterr().out.splitlines()] == ["ctrl.u", "ctrl.k"]

    assert mdxml.main(["variables", str(tmp_path / "missing.xml")]) == 1
    assert capsys.readouterr().err.startswith("mdxml: error:")
