"""Issue #11: Tool Annotations, skipped by default, kept as raw XML with annotations=True."""

from __future__ import annotations

import json
import tracemalloc
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

import mdxml
from mdxml import ParseError, fmi2, fmi3, iter_variables, read, read_header, to_dict

DATA = Path(__file__).parent / "data"
REFERENCES = sorted((DATA / "reference_fmus").glob("*/FMI[23].xml"))

# Content that a naive approach would get wrong: a ">" inside a quoted attribute of the
# annotation element itself, entities, a comment, CDATA, non-ASCII text, nested elements.
TRICKY = (
    '\n  <Data unit="m&gt;s" note=\'a "quoted" value\'>x &amp; y &lt; z</Data>'
    "\n  <!-- keep me -->"
    "\n  <![CDATA[<raw> & stuff]]>"
    "\n  <Ünïcode>héllo · 世界</Ünïcode>\n"
)

FMI2_DOC = f"""<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="2.0" modelName="A2" guid="g">
  <VendorAnnotations>
    <Tool name="Tricky" weird="a > b">{TRICKY}</Tool>
    <Tool name="Empty"/>
    <Tool name="Second"><Simple/></Tool>
  </VendorAnnotations>
  <ModelVariables>
    <ScalarVariable name="v1" valueReference="1" causality="output">
      <Real start="1"/>
      <Annotations><Tool name="VarTool"><Setting key="k" value="v"/></Tool></Annotations>
    </ScalarVariable>
    <ScalarVariable name="v2" valueReference="2"><Real/></ScalarVariable>
  </ModelVariables>
  <ModelStructure/>
</fmiModelDescription>
""".encode()

FMI3_DOC = f"""<?xml version="1.0" encoding="UTF-8"?>
<fmiModelDescription fmiVersion="3.0" modelName="A3" instantiationToken="t">
  <UnitDefinitions>
    <Unit name="m"><Annotations><Annotation type="unit.level"><Skipped/></Annotation></Annotations></Unit>
  </UnitDefinitions>
  <ModelVariables>
    <Float64 name="x" valueReference="1">
      <Annotations>
        <Annotation type="mixed">some text <b>bold</b> more text</Annotation>
        <Annotation type="empty"/>
      </Annotations>
    </Float64>
    <Clock name="c" valueReference="2" causality="input" intervalVariability="triggered">
      <Annotations><Annotation type="clock">{TRICKY}</Annotation></Annotations>
    </Clock>
    <Int32 name="n" valueReference="3"/>
  </ModelVariables>
  <ModelStructure/>
  <Annotations>
    <Annotation type="com.example.model">{TRICKY}</Annotation>
  </Annotations>
</fmiModelDescription>
""".encode()


def read2(src: bytes, **options: Any) -> fmi2.ModelDescription:
    md = read(src, **options)
    assert isinstance(md, fmi2.ModelDescription)
    return md


def read3(src: bytes, **options: Any) -> fmi3.ModelDescription:
    md = read(src, **options)
    assert isinstance(md, fmi3.ModelDescription)
    return md


# --- Default: skipped, never kept -----------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_default_leaves_annotations_none(path: Path) -> None:
    md = read(path)
    if isinstance(md, fmi2.ModelDescription):
        assert md.header.vendor_annotations is None
    else:
        assert md.annotations is None
    assert all(v.annotations is None for v in md.variables)


def test_default_never_captures_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object) -> None:
        raise AssertionError("annotation bytes were kept")

    monkeypatch.setattr("mdxml._reader._ExpatPosition.keep_from", fail)
    for doc in (FMI2_DOC, FMI3_DOC):
        read(doc, strict=True)
        read_header(doc)
        list(iter_variables(doc))


def test_default_skips_a_huge_annotation_without_keeping_it() -> None:
    huge = "<x>" + "y" * (8 * 1024 * 1024) + "</x>"
    doc = FMI2_DOC.replace(b"<Simple/>", huge.encode())
    tracemalloc.start()
    try:
        assert read_header(doc).model_name == "A2"
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024  # streamed past; never accumulated


def test_default_output_has_no_annotations_keys() -> None:
    data = to_dict(read2(FMI2_DOC))
    assert "vendor_annotations" not in data["header"]
    assert all("annotations" not in v for v in data["variables"])


# --- annotations=True: exact raw XML --------------------------------------------------------


def test_fmi2_vendor_annotations_are_exact() -> None:
    header = read_header(FMI2_DOC, annotations=True)
    assert isinstance(header, fmi2.ModelHeader)
    assert header.vendor_annotations == (
        fmi2.ToolAnnotation(name="Tricky", xml=TRICKY),
        fmi2.ToolAnnotation(name="Empty", xml=""),
        fmi2.ToolAnnotation(name="Second", xml="<Simple/>"),
    )


def test_fmi2_variable_annotations_are_exact() -> None:
    v1, v2 = iter_variables(FMI2_DOC, annotations=True)
    assert v1.annotations == (fmi2.ToolAnnotation(name="VarTool", xml='<Setting key="k" value="v"/>'),)
    assert v2.annotations == ()  # requested, but the variable has none


def test_fmi3_variable_annotations_are_exact() -> None:
    x, c, n = iter_variables(FMI3_DOC, annotations=True)
    assert x.annotations == (
        fmi3.Annotation(type="mixed", xml="some text <b>bold</b> more text"),
        fmi3.Annotation(type="empty", xml=""),
    )
    assert c.annotations == (fmi3.Annotation(type="clock", xml=TRICKY),)
    assert n.annotations == ()


def test_fmi3_model_level_annotations_come_from_read_only() -> None:
    md = read3(FMI3_DOC, annotations=True)
    assert md.annotations == (fmi3.Annotation(type="com.example.model", xml=TRICKY),)
    assert md.variables == tuple(iter_variables(FMI3_DOC, annotations=True))
    # read_header and iter_variables stop before them.
    assert not hasattr(read_header(FMI3_DOC, annotations=True), "annotations")


def test_fmi3_annotations_on_other_elements_stay_skipped() -> None:
    header = read_header(FMI3_DOC, annotations=True, strict=True)
    assert isinstance(header, fmi3.ModelHeader)
    assert header.unit_definitions["m"] == fmi3.Unit(name="m")


def test_raw_xml_can_be_parsed_again() -> None:
    annotations = read2(FMI2_DOC, annotations=True).header.vendor_annotations
    assert annotations is not None
    tricky = annotations[0]
    wrapped = ET.fromstring(f"<wrap>{tricky.xml}</wrap>")
    data = wrapped.find("Data")
    assert data is not None
    assert data.get("unit") == "m>s"
    assert data.text == "x & y < z"
    assert wrapped.find("Ünïcode") is not None


def test_annotations_spanning_many_chunks() -> None:
    big = "<Blob>" + "0123456789" * 30_000 + "</Blob>"  # ~300 KB, several 64 KB chunks
    doc = FMI2_DOC.replace(b"<Simple/>", big.encode())
    header = read_header(doc, annotations=True)
    assert isinstance(header, fmi2.ModelHeader)
    assert header.vendor_annotations is not None
    assert header.vendor_annotations[2].xml == big


@pytest.mark.parametrize("pad", [0, 1, 7, 13, 50])
def test_start_tags_split_across_chunk_boundaries(pad: int) -> None:
    # Push the annotation's start tag across the 64 KB chunk boundary at several offsets.
    from mdxml._reader import CHUNK_SIZE

    prefix = FMI2_DOC.index(b'<Tool name="Tricky"')
    filler = b"<!--" + b" " * (CHUNK_SIZE - prefix - 8 - pad) + b"-->"
    doc = FMI2_DOC[:prefix] + filler + FMI2_DOC[prefix:]
    header = read_header(doc, annotations=True)
    assert isinstance(header, fmi2.ModelHeader)
    assert header.vendor_annotations is not None
    assert header.vendor_annotations[0].xml == TRICKY


def test_filtered_out_variables_keep_nothing() -> None:
    (v1,) = iter_variables(FMI2_DOC, annotations=True, causality="output")
    assert v1.name == "v1"
    assert v1.annotations is not None


def test_annotations_in_json_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = to_dict(read3(FMI3_DOC, annotations=True))
    assert data["annotations"] == [{"type": "com.example.model", "xml": TRICKY}]
    json.dumps(data, allow_nan=False)

    path = tmp_path / "md.xml"
    path.write_bytes(FMI2_DOC)
    assert mdxml.main(["variables", str(path), "--annotations"]) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[0])
    assert first["annotations"] == [{"name": "VarTool", "xml": '<Setting key="k" value="v"/>'}]
    assert mdxml.main(["header", str(path), "--annotations"]) == 0
    assert [t["name"] for t in json.loads(capsys.readouterr().out)["vendor_annotations"]] == [
        "Tricky",
        "Empty",
        "Second",
    ]


# --- Lenient vs strict ----------------------------------------------------------------------


# The tricky <Tool> carries an attribute strict mode would reject first, so strict tests drop it.
VALID_FMI2_DOC = FMI2_DOC.replace(b' weird="a > b"', b"")


def test_tool_without_name_is_lenient_only() -> None:
    doc = VALID_FMI2_DOC.replace(b'<Tool name="Second">', b"<Tool>")
    header = read_header(doc, annotations=True)
    assert isinstance(header, fmi2.ModelHeader)
    assert header.vendor_annotations is not None
    assert header.vendor_annotations[2] == fmi2.ToolAnnotation(name="", xml="<Simple/>")
    with pytest.raises(ParseError, match="'name'"):
        read_header(doc, annotations=True, strict=True)


def test_unknown_attribute_on_annotation_is_lenient_only() -> None:
    doc = FMI3_DOC.replace(b'<Annotation type="empty"/>', b'<Annotation type="empty" extra="1"/>')
    assert len(list(iter_variables(doc, annotations=True))) == 3
    with pytest.raises(ParseError, match="extra"):
        list(iter_variables(doc, annotations=True, strict=True))


def test_unknown_element_in_annotations_list_is_lenient_only() -> None:
    doc = VALID_FMI2_DOC.replace(b'<Tool name="Empty"/>', b"<NotATool/>")
    header = read_header(doc, annotations=True)
    assert isinstance(header, fmi2.ModelHeader)
    assert [t.name for t in header.vendor_annotations or ()] == ["Tricky", "Second"]
    with pytest.raises(ParseError, match="<NotATool>"):
        read_header(doc, annotations=True, strict=True)


def test_annotations_and_default_agree_on_everything_else() -> None:
    for doc in (FMI2_DOC, FMI3_DOC):
        with_annotations = to_dict(read(doc, annotations=True))
        without = to_dict(read(doc))
        with_annotations.pop("annotations", None)
        with_annotations["header"].pop("vendor_annotations", None)
        for variable in with_annotations["variables"]:
            variable.pop("annotations")
        assert with_annotations == without
