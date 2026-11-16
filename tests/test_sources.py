"""Issue #3: every input kind gives the same Model Header."""

from __future__ import annotations

import io
import os
import shutil
import sys
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO

import pytest

from mdxml import ParseError, Source, read_header
from mdxml.fmi2 import ModelHeader

XML = Path(__file__).parent / "data" / "reference_fmus" / "BouncingBall" / "FMI2.xml"
XML_BYTES = XML.read_bytes()
EXPECTED = read_header(XML)


def make_zip(entries: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


FMU_BYTES = make_zip({"modelDescription.xml": XML_BYTES, "binaries/linux64/BouncingBall.so": b"\x7fELF"})


class ForwardOnly(io.RawIOBase):
    """A stream that can't be rewound, like a raw request body."""

    def __init__(self, data: bytes) -> None:
        self._inner = io.BytesIO(data)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(size)


class NoSeekableMethod:
    """A bare object with only ``read``."""

    def __init__(self, data: bytes) -> None:
        self._inner = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(size)


@pytest.fixture
def fmu_path(tmp_path: Path) -> Path:
    path = tmp_path / "BouncingBall.fmu"
    path.write_bytes(FMU_BYTES)
    return path


@pytest.fixture
def fmu_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "unzipped"
    directory.mkdir()
    shutil.copy(XML, directory / "modelDescription.xml")
    return directory


# --- All five input kinds -------------------------------------------------------------------


SOURCES: dict[str, Callable[[Path, Path], Source]] = {
    "fmu path": lambda fmu, d: fmu,
    "fmu str path": lambda fmu, d: str(fmu),
    "directory": lambda fmu, d: d,
    "xml path": lambda fmu, d: XML,
    "zip stream": lambda fmu, d: io.BytesIO(FMU_BYTES),
    "xml stream": lambda fmu, d: io.BytesIO(XML_BYTES),
    "forward-only xml stream": lambda fmu, d: ForwardOnly(XML_BYTES),
    "object with only read()": lambda fmu, d: NoSeekableMethod(XML_BYTES),
    "zip bytes": lambda fmu, d: FMU_BYTES,
    "xml bytes": lambda fmu, d: XML_BYTES,
    "zip bytearray": lambda fmu, d: bytearray(FMU_BYTES),
    "xml memoryview": lambda fmu, d: memoryview(XML_BYTES),
}


@pytest.mark.parametrize("kind", SOURCES)
def test_every_input_kind_gives_the_same_header(kind: str, fmu_path: Path, fmu_dir: Path) -> None:
    assert read_header(SOURCES[kind](fmu_path, fmu_dir)) == EXPECTED


def test_open_file_object(fmu_path: Path) -> None:
    with open(fmu_path, "rb") as file:
        assert read_header(file) == EXPECTED
        assert not file.closed


def test_callers_stream_is_left_open() -> None:
    for stream in (io.BytesIO(FMU_BYTES), io.BytesIO(XML_BYTES)):
        read_header(stream)
        assert not stream.closed


def test_stored_zip_entries_work() -> None:
    assert read_header(make_zip({"modelDescription.xml": XML_BYTES}, zipfile.ZIP_STORED)) == EXPECTED


# --- Detection by magic bytes, not extension ------------------------------------------------


@pytest.mark.parametrize("name", ["model.zip", "model", "model.xml", "model.FMU"])
def test_zip_detected_by_content_not_extension(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(FMU_BYTES)
    assert read_header(path) == EXPECTED


def test_xml_with_fmu_extension_is_read_as_xml(tmp_path: Path) -> None:
    path = tmp_path / "actually-xml.fmu"
    path.write_bytes(XML_BYTES)
    assert read_header(path) == EXPECTED


def test_corrupt_zip_is_a_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.fmu"
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(ParseError, match="zip archive"):
        read_header(path)


# --- Streams that can't be rewound ----------------------------------------------------------


@pytest.mark.parametrize("make", [ForwardOnly, NoSeekableMethod])
def test_forward_only_zip_stream_is_a_type_error(make: Callable[[bytes], IO[bytes]]) -> None:
    with pytest.raises(TypeError, match="needs a seekable stream"):
        read_header(make(FMU_BYTES))


def test_text_stream_is_a_type_error() -> None:
    with pytest.raises(TypeError, match="binary stream"):
        read_header(io.StringIO(XML_BYTES.decode()))  # type: ignore[arg-type]


def test_unsupported_source_type() -> None:
    with pytest.raises(TypeError, match="int"):
        read_header(42)  # type: ignore[arg-type]


# --- member= and missing Model Descriptions -------------------------------------------------


def test_member_inside_zip() -> None:
    data = make_zip({"nested/md.xml": XML_BYTES})
    assert read_header(data, member="nested/md.xml") == EXPECTED


def test_member_inside_directory(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    shutil.copy(XML, tmp_path / "nested" / "md.xml")
    assert read_header(tmp_path, member="nested/md.xml") == EXPECTED


def test_zip_without_model_description() -> None:
    with pytest.raises(FileNotFoundError, match="modelDescription.xml"):
        read_header(make_zip({"other.txt": b"x"}))


def test_empty_zip_has_no_model_description() -> None:
    with pytest.raises(FileNotFoundError):
        read_header(make_zip({}))


def test_missing_member_in_zip() -> None:
    with pytest.raises(FileNotFoundError, match="nope.xml"):
        read_header(FMU_BYTES, member="nope.xml")


def test_directory_without_model_description(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="modelDescription.xml"):
        read_header(tmp_path)


def test_missing_member_in_directory(fmu_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nope.xml"):
        read_header(fmu_dir, member="nope.xml")


@pytest.mark.parametrize("src", [XML_BYTES, XML], ids=["bytes", "path"])
def test_member_with_raw_xml_is_rejected(src: Source) -> None:
    with pytest.raises(ValueError, match="member="):
        read_header(src, member="modelDescription.xml")


# --- Nothing is written to disk -------------------------------------------------------------

_WRITE_MODES = frozenset("wax+")


@pytest.fixture
def disk_writes() -> Iterator[list[str]]:
    """Record every file opened for writing while the test runs (via an audit hook)."""
    writes: list[str] = []
    active = [True]

    def hook(event: str, args: tuple[object, ...]) -> None:
        if active[0] and event == "open" and len(args) >= 2:
            path, mode = args[0], args[1]
            if isinstance(mode, str) and _WRITE_MODES & set(mode):
                writes.append(str(path))
            elif isinstance(mode, int) and mode & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):  # os.open flags
                writes.append(str(path))

    sys.addaudithook(hook)  # audit hooks can't be removed, so the hook switches itself off
    try:
        yield writes
    finally:
        active[0] = False


def test_nothing_is_written_to_disk(fmu_path: Path, fmu_dir: Path, disk_writes: list[str]) -> None:
    for make in SOURCES.values():
        read_header(make(fmu_path, fmu_dir))
    read_header(make_zip({"nested/md.xml": XML_BYTES}), member="nested/md.xml")

    assert disk_writes == []


def test_cli_reads_fmu_with_member(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import json

    import mdxml

    path = tmp_path / "nested.fmu"
    path.write_bytes(make_zip({"nested/md.xml": XML_BYTES}))

    assert mdxml.main(["header", str(path), "--member", "nested/md.xml"]) == 0
    assert json.loads(capsys.readouterr().out)["model_name"] == "BouncingBall"


def test_header_type() -> None:
    assert isinstance(EXPECTED, ModelHeader)


def test_disk_write_detector_catches_writes(tmp_path: Path, disk_writes: list[str]) -> None:
    (tmp_path / "written.txt").write_text("x")
    assert any(path.endswith("written.txt") for path in disk_writes)
