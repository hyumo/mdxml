"""Issue #2: read_header for FMI 2 from an .xml path, plus to_dict and the CLI."""

from __future__ import annotations

import dataclasses
import importlib
import json
import pkgutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import mdxml
from mdxml import ParseError, UnsupportedFmiVersion, read_header, to_dict
from mdxml.fmi2 import ModelHeader, VariableNamingConvention

REFERENCE_FMUS = Path(__file__).parent / "data" / "reference_fmus"
FMI2_XMLS = sorted(REFERENCE_FMUS.glob("*/FMI2.xml"))


def write_xml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "modelDescription.xml"
    path.write_text(text, encoding="utf-8")
    return path


def fmi2_xml(root_attrs: str = "", after_model_variables: str = "<ScalarVariable/></ModelVariables></fmiModelDescription>") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="{{G}}" {root_attrs}>\n'
        "  <DefaultExperiment stopTime=\"1\"/>\n"
        "  <ModelVariables>" + after_model_variables
    )


# --- Reference FMUs -------------------------------------------------------------------------


def test_bouncing_ball_root_attributes() -> None:
    header = read_header(REFERENCE_FMUS / "BouncingBall" / "FMI2.xml")

    assert header == ModelHeader(
        fmi_version="2.0",
        model_name="BouncingBall",
        guid="{1AE5E10D-9521-4DE3-80B9-D0EAAA7D5AF1}",
        description="This model calculates the trajectory, over time, of a ball dropped from a height of 1 m",
        generation_tool="Reference FMUs (development build)",
        number_of_event_indicators=1,
    )
    assert header.variable_naming_convention is VariableNamingConvention.FLAT


@pytest.mark.parametrize("path", FMI2_XMLS, ids=lambda p: p.parent.name)
def test_every_fmi2_reference_header_parses(path: Path) -> None:
    header = read_header(path)

    assert header.fmi_version == "2.0"
    assert header.model_name
    assert header.guid.startswith("{")
    assert isinstance(header.number_of_event_indicators, int)


def test_accepts_str_paths() -> None:
    path = REFERENCE_FMUS / "Dahlquist" / "FMI2.xml"
    assert read_header(str(path)) == read_header(path)


# --- Typed root attributes ------------------------------------------------------------------


def test_all_root_attributes_are_typed(tmp_path: Path) -> None:
    path = write_xml(
        tmp_path,
        fmi2_xml(
            'description="d" author="a" version="1.4.1" copyright="c" license="BSD" '
            'generationTool="tool" generationDateAndTime="2026-11-16T08:30:00Z" '
            'variableNamingConvention="structured" numberOfEventIndicators="3"'
        ),
    )

    header = read_header(path)

    assert header == ModelHeader(
        fmi_version="2.0",
        model_name="M",
        guid="{G}",
        description="d",
        author="a",
        version="1.4.1",
        copyright="c",
        license="BSD",
        generation_tool="tool",
        generation_date_and_time=datetime(2026, 11, 16, 8, 30, tzinfo=timezone.utc),
        variable_naming_convention=VariableNamingConvention.STRUCTURED,
        number_of_event_indicators=3,
    )


def test_datetime_keeps_its_offset(tmp_path: Path) -> None:
    header = read_header(write_xml(tmp_path, fmi2_xml('generationDateAndTime="2026-11-16T08:30:00+02:00"')))
    assert header.generation_date_and_time == datetime(2026, 11, 16, 8, 30, tzinfo=timezone(timedelta(hours=2)))


def test_unknown_naming_convention_stays_a_string(tmp_path: Path) -> None:
    header = read_header(write_xml(tmp_path, fmi2_xml('variableNamingConvention="dotted"')))
    assert header.variable_naming_convention == "dotted"
    assert not isinstance(header.variable_naming_convention, VariableNamingConvention)


def test_unknown_root_attributes_are_ignored(tmp_path: Path) -> None:
    header = read_header(write_xml(tmp_path, fmi2_xml('vendorThing="x"')))
    assert header.model_name == "M"


def test_missing_required_text_attributes_become_empty(tmp_path: Path) -> None:
    path = write_xml(tmp_path, '<fmiModelDescription fmiVersion="2.0"><ModelVariables/></fmiModelDescription>')
    header = read_header(path)
    assert (header.model_name, header.guid) == ("", "")


def test_header_is_frozen_with_slots() -> None:
    header = read_header(REFERENCE_FMUS / "BouncingBall" / "FMI2.xml")
    with pytest.raises(dataclasses.FrozenInstanceError):
        header.model_name = "other"  # type: ignore[misc]
    assert not hasattr(header, "__dict__")


# --- Stops at <ModelVariables> --------------------------------------------------------------


def test_parsing_stops_at_model_variables(tmp_path: Path) -> None:
    # Everything after <ModelVariables> is broken XML. If the parser read any of it, it would fail.
    path = write_xml(tmp_path, fmi2_xml('numberOfEventIndicators="2"', after_model_variables="<<< not xml &&& </nope>"))
    assert read_header(path).number_of_event_indicators == 2


def test_parsing_stops_before_reading_the_rest_of_a_large_file(tmp_path: Path) -> None:
    variables = "".join(f'<ScalarVariable name="v{i}" valueReference="{i}"><Real/></ScalarVariable>' for i in range(50_000))
    path = write_xml(tmp_path, fmi2_xml(after_model_variables=variables + "</ModelVariables></fmiModelDescription>"))
    read_bytes: list[int] = []

    original_open = open

    class CountingReads:
        def __init__(self, file: Path) -> None:
            self._f = original_open(file, "rb")

        def read(self, size: int = -1) -> bytes:
            data = self._f.read(size)
            read_bytes.append(len(data))
            return data

        def __enter__(self) -> CountingReads:
            return self

        def __exit__(self, *exc: object) -> None:
            self._f.close()

    def counting_open(file: Path, mode: str) -> CountingReads:
        assert mode == "rb"
        return CountingReads(file)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("mdxml._header.open", counting_open, raising=False)
        read_header(path)

    assert path.stat().st_size > 1_000_000
    assert sum(read_bytes) <= 64 * 1024


# --- Errors ---------------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["1.0", "4.0", "garbage"])
def test_unsupported_versions(tmp_path: Path, version: str) -> None:
    path = write_xml(tmp_path, f'<fmiModelDescription fmiVersion="{version}" modelName="M" guid="g"/>')
    with pytest.raises(UnsupportedFmiVersion) as info:
        read_header(path)
    assert info.value.fmi_version == version
    assert isinstance(info.value, mdxml.MdxmlError)


def test_fmi3_is_not_supported_yet() -> None:
    # Replaced by real FMI 3 support in issue #6.
    with pytest.raises(UnsupportedFmiVersion, match="not implemented yet"):
        read_header(REFERENCE_FMUS / "BouncingBall" / "FMI3.xml")


def test_malformed_xml_reports_line_and_column(tmp_path: Path) -> None:
    path = write_xml(tmp_path, '<?xml version="1.0"?>\n<fmiModelDescription fmiVersion="2.0"\n   modelName=M>')
    with pytest.raises(ParseError) as info:
        read_header(path)
    assert (info.value.line, info.value.column) == (3, 14)
    assert isinstance(info.value, ValueError)
    assert "line 3, column 14" in str(info.value)


def test_truncated_file_is_a_parse_error(tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        read_header(write_xml(tmp_path, '<fmiModelDescription fmiVersion="2.0" modelName="M" guid="g">'))


def test_wrong_root_element(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="expected <fmiModelDescription>") as info:
        read_header(write_xml(tmp_path, '<?xml version="1.0"?>\n<fmiBuildDescription fmiVersion="3.0"/>'))
    assert info.value.line == 2


def test_missing_fmi_version(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="no fmiVersion"):
        read_header(write_xml(tmp_path, '<fmiModelDescription modelName="M" guid="g"/>'))


def test_invalid_typed_value_reports_where(tmp_path: Path) -> None:
    path = write_xml(tmp_path, '<?xml version="1.0"?>\n\n<fmiModelDescription fmiVersion="2.0" numberOfEventIndicators="-1"/>')
    with pytest.raises(ParseError, match="numberOfEventIndicators") as info:
        read_header(path)
    assert info.value.line == 3


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_header(tmp_path / "nope.xml")


# --- to_dict --------------------------------------------------------------------------------


def test_to_dict_is_json_ready_and_drops_none(tmp_path: Path) -> None:
    path = write_xml(tmp_path, fmi2_xml('generationDateAndTime="2026-11-16T08:30:00Z"'))
    data = to_dict(read_header(path))

    assert data == {
        "fmi_version": "2.0",
        "model_name": "M",
        "guid": "{G}",
        "generation_date_and_time": "2026-11-16T08:30:00+00:00",
        "variable_naming_convention": "flat",
    }
    assert json.loads(json.dumps(data)) == data


def test_to_dict_turns_tuples_into_lists() -> None:
    @dataclasses.dataclass(frozen=True)
    class Holder:
        items: tuple[VariableNamingConvention, ...]

    assert to_dict(Holder((VariableNamingConvention.FLAT,))) == {"items": ["flat"]}


# --- CLI ------------------------------------------------------------------------------------


def test_cli_header_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    path = REFERENCE_FMUS / "BouncingBall" / "FMI2.xml"

    assert mdxml.main(["header", str(path)]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["model_name"] == "BouncingBall"
    assert out["number_of_event_indicators"] == 1


def test_cli_reports_errors_on_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mdxml.main(["header", str(tmp_path / "missing.xml")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("mdxml: error:")


# --- No module-level mutable state ----------------------------------------------------------

MUTABLE = (list, dict, set, bytearray)


def test_no_module_level_mutable_state() -> None:
    offenders: list[str] = []
    for info in pkgutil.walk_packages(mdxml.__path__, prefix="mdxml."):
        if info.name == "mdxml.__main__":
            continue
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if name.startswith("__") and name.endswith("__"):
                continue
            if isinstance(value, MUTABLE):
                offenders.append(f"{info.name}.{name}")
    assert offenders == []
