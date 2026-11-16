"""Streaming XML reading on top of expat.

A reader drives a :class:`Handler` with start/end element events and stops
feeding expat as soon as the handler says it's done, so nothing after the
part a caller asked for is ever read (see ADR 0001).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Protocol
from xml.parsers import expat

from mdxml._errors import ParseError, UnsafeInput
from mdxml._source import Readable

CHUNK_SIZE = 64 * 1024
DEFAULT_MAX_XML_BYTES = 256 * 1024 * 1024


class Stop(Exception):
    """Raised by a handler to end parsing early. Never escapes this module."""


class Handler(Protocol):
    def start(self, name: str, attrs: dict[str, str]) -> None: ...
    def end(self, name: str) -> None: ...


class Position(Protocol):
    """Where the parser currently is, for error messages."""

    @property
    def line(self) -> int: ...
    @property
    def column(self) -> int: ...


class _ExpatPosition:
    __slots__ = ("_parser",)

    def __init__(self, parser: expat.XMLParserType) -> None:
        self._parser = parser

    @property
    def line(self) -> int:
        return self._parser.CurrentLineNumber

    @property
    def column(self) -> int:
        return self._parser.CurrentColumnNumber + 1


def check_max_xml_bytes(max_xml_bytes: object) -> int:
    """Validate a caller's ``max_xml_bytes``; it arrives from untyped callers too."""
    if isinstance(max_xml_bytes, bool) or not isinstance(max_xml_bytes, int) or max_xml_bytes <= 0:
        raise ValueError(f"max_xml_bytes must be a positive int, got {max_xml_bytes!r}")
    return max_xml_bytes


def _refuse_doctype(doctype_name: str, *_: object) -> None:
    raise UnsafeInput(f"refusing a DOCTYPE declaration (<!DOCTYPE {doctype_name}>); Model Descriptions never need one")


def _refuse_entity(entity_name: str, *_: object) -> None:
    raise UnsafeInput(f"refusing entity declaration {entity_name!r}")


def _refuse_external_entity(*_: object) -> int:
    raise UnsafeInput("refusing to resolve an external entity")


def _create_parser() -> expat.XMLParserType:
    """Create an expat parser that refuses DOCTYPEs and entities instead of processing them."""
    parser = expat.ParserCreate()
    # Entity declarations can only appear inside a DOCTYPE, so refusing the DOCTYPE at its first
    # token blocks entity bombs and XXE before any declaration is read. The other handlers are
    # a second line of defence.
    parser.StartDoctypeDeclHandler = _refuse_doctype
    parser.EntityDeclHandler = _refuse_entity
    parser.ExternalEntityRefHandler = _refuse_external_entity
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    return parser


def feed(
    stream: Readable,
    handler: Handler,
    position_sink: list[Position],
    *,
    max_xml_bytes: int = DEFAULT_MAX_XML_BYTES,
) -> Generator[None, None, None]:
    """Parse ``stream`` with ``handler`` one chunk at a time, yielding after each chunk.

    This lets a caller hand out what the handler built from each chunk before
    reading more, so memory stays bounded by the chunk size. The generator
    ends when the document ends or the handler raises :class:`Stop`.

    ``position_sink`` receives the live parser position before parsing starts,
    so the handler can attach line and column to its own errors. At most
    ``max_xml_bytes`` bytes are read; reaching more raises :class:`UnsafeInput`.
    """
    parser = _create_parser()
    parser.StartElementHandler = handler.start
    parser.EndElementHandler = handler.end
    position_sink.append(_ExpatPosition(parser))
    total = 0
    try:
        # Ask for one byte more than the budget allows, so going over is detected
        # without ever reading (or decompressing) much past the limit.
        while chunk := stream.read(min(CHUNK_SIZE, max_xml_bytes - total + 1)):
            total += len(chunk)
            if total > max_xml_bytes:
                raise UnsafeInput(f"Model Description is larger than max_xml_bytes={max_xml_bytes}")
            parser.Parse(chunk, False)  # noqa: FBT003 - expat only accepts isfinal positionally
            yield
        parser.Parse(b"", True)  # noqa: FBT003
    except Stop:
        return
    except expat.ExpatError as exc:
        raise ParseError(
            expat.ErrorString(exc.code) if exc.code else str(exc),
            line=exc.lineno,
            column=exc.offset + 1,
        ) from None


def run(
    stream: Readable,
    handler: Handler,
    position_sink: list[Position],
    *,
    max_xml_bytes: int = DEFAULT_MAX_XML_BYTES,
) -> None:
    """Parse ``stream`` with ``handler`` until the document ends or the handler raises :class:`Stop`."""
    for _ in feed(stream, handler, position_sink, max_xml_bytes=max_xml_bytes):
        pass
