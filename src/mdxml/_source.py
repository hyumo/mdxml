"""Opening any supported input as a binary stream of Model Description XML.

Supported inputs:

- a path to a ``.fmu`` zip (any extension; detected by magic bytes),
- a path to an unzipped FMU directory,
- a path to a ``modelDescription.xml`` file,
- a binary file-like object holding a zip or raw XML,
- ``bytes``, ``bytearray`` or ``memoryview`` holding a zip or raw XML.

Zip entries are streamed straight out of the archive; nothing is extracted to disk.
"""

from __future__ import annotations

import io
import os
import zipfile
import zlib
from collections.abc import Generator
from contextlib import contextmanager
from typing import IO, Protocol, Union, cast

from mdxml._errors import ParseError, UnsafeInput

MODEL_DESCRIPTION = "modelDescription.xml"

# Local file header, and end of central directory (an empty archive).
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")
_MAGIC_LENGTH = 4


class Readable(Protocol):
    """A binary stream: anything with ``read(size) -> bytes``.

    Zipped input additionally needs ``seekable()``, ``seek()`` and ``tell()``.
    """

    def read(self, size: int = -1, /) -> bytes: ...


Source = Union[str, "os.PathLike[str]", bytes, bytearray, memoryview, Readable]
"""Anything :func:`mdxml.read_header` and friends accept as input."""


class _Prefixed:
    """A forward-only stream that replays bytes already read for sniffing, then continues."""

    __slots__ = ("_prefix", "_rest")

    def __init__(self, prefix: bytes, rest: Readable) -> None:
        self._prefix = prefix
        self._rest = rest

    def read(self, size: int = -1, /) -> bytes:
        if not self._prefix:
            return self._rest.read(size)
        if size < 0:
            data, self._prefix = self._prefix + self._rest.read(), b""
            return data
        data, self._prefix = self._prefix[:size], self._prefix[size:]
        return data


class _ZipEntry:
    """A zip entry stream that reports corrupt archive data as :class:`ParseError`.

    zipfile only notices some corruption (a bad CRC, a broken deflate stream, an
    entry longer or shorter than its header claims) while reading, so the
    translation has to happen here rather than when the entry is opened.
    """

    __slots__ = ("_entry", "_name", "_origin")

    def __init__(self, entry: Readable, name: str, origin: str) -> None:
        self._entry = entry
        self._name = name
        self._origin = origin

    def read(self, size: int = -1, /) -> bytes:
        try:
            return self._entry.read(size)
        except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
            raise ParseError(f"corrupt zip data in {self._name!r} in {self._origin}: {exc}") from None


def _is_zip(prefix: bytes) -> bool:
    return prefix.startswith(_ZIP_MAGIC)


def _is_seekable(stream: Readable) -> bool:
    seekable = getattr(stream, "seekable", None)
    return bool(seekable()) if callable(seekable) else False


def _read_prefix(stream: Readable) -> bytes:
    prefix: object = stream.read(_MAGIC_LENGTH)
    if not isinstance(prefix, bytes):  # pyright: ignore[reportUnnecessaryIsInstance] - text streams lie about their type
        raise TypeError(
            f"expected a binary stream, got one returning {type(prefix).__name__}; open the file in 'rb' mode"
        )
    return prefix


def _reject_member(member: str | None, origin: str) -> None:
    if member is not None:
        raise ValueError(f"member={member!r} only applies to zip archives and directories, but {origin} is raw XML")


@contextmanager
def _zip_member(
    stream: IO[bytes], member: str | None, origin: str, max_xml_bytes: int
) -> Generator[Readable, None, None]:
    name = member if member is not None else MODEL_DESCRIPTION
    try:
        archive = zipfile.ZipFile(stream)
    except zipfile.BadZipFile as exc:
        raise ParseError(f"{origin} looks like a zip archive but can't be opened: {exc}") from None
    with archive:
        try:
            info = archive.getinfo(name)
        except KeyError:
            raise FileNotFoundError(f"{name!r} not found in {origin}") from None
        # Cheap early rejection. zipfile never yields more than file_size bytes for an entry,
        # and the reader counts the bytes it actually gets, so a lying header can't get past either.
        if info.file_size > max_xml_bytes:
            raise UnsafeInput(
                f"{name!r} in {origin} decompresses to {info.file_size} bytes, more than max_xml_bytes={max_xml_bytes}"
            )
        try:
            entry = archive.open(info)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
            # Bad local header, unsupported compression method, or an encrypted entry.
            raise ParseError(f"can't read {name!r} in {origin}: {exc}") from None
        with entry:
            yield _ZipEntry(entry, name, origin)


@contextmanager
def _open_stream(
    stream: Readable, member: str | None, origin: str, max_xml_bytes: int
) -> Generator[Readable, None, None]:
    if _is_seekable(stream):
        seekable = cast(IO[bytes], stream)
        start = seekable.tell()
        prefix = _read_prefix(stream)
        seekable.seek(start)
        if _is_zip(prefix):
            with _zip_member(seekable, member, origin, max_xml_bytes) as entry:
                yield entry
            return
        _reject_member(member, origin)
        yield stream
        return

    prefix = _read_prefix(stream)
    if _is_zip(prefix):
        raise TypeError(
            f"{origin} is a zip archive in a stream that can't be rewound; "
            "zipped input needs a seekable stream (e.g. io.BytesIO or a regular file)"
        )
    _reject_member(member, origin)
    yield _Prefixed(prefix, stream)


@contextmanager
def open_source(src: Source, member: str | None, max_xml_bytes: int) -> Generator[Readable, None, None]:
    """Yield a binary stream of the Model Description XML in ``src``.

    Only the Model Description is opened; no other archive member is read.
    Streams passed in by the caller are never closed. Files mdxml opens itself are.
    """
    if isinstance(src, (bytes, bytearray, memoryview)):
        with _open_stream(io.BytesIO(src), member, "the given bytes", max_xml_bytes) as stream:
            yield stream
        return

    if isinstance(src, (str, os.PathLike)):
        path = os.fspath(src)
        if os.path.isdir(path):
            path = os.path.join(path, member if member is not None else MODEL_DESCRIPTION)
            if not os.path.isfile(path):
                raise FileNotFoundError(f"{path!r} not found in FMU directory {os.fspath(src)!r}")
            member = None
        with open(path, "rb") as file, _open_stream(file, member, repr(path), max_xml_bytes) as stream:
            yield stream
        return

    if not callable(getattr(src, "read", None)):
        raise TypeError(f"can't read a Model Description from {type(src).__name__}")
    with _open_stream(src, member, "the given stream", max_xml_bytes) as stream:
        yield stream
