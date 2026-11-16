"""Streaming XML reading on top of expat.

A reader drives a :class:`Handler` with start/end element events and stops
feeding expat as soon as the handler says it's done, so nothing after the
part a caller asked for is ever read (see ADR 0001).
"""

from __future__ import annotations

from typing import Protocol
from xml.parsers import expat

from mdxml._errors import ParseError
from mdxml._source import Readable

CHUNK_SIZE = 64 * 1024


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


def run(stream: Readable, handler: Handler, position_sink: list[Position]) -> None:
    """Parse ``stream`` with ``handler`` until the document ends or the handler raises :class:`Stop`.

    ``position_sink`` receives the live parser position before parsing starts,
    so the handler can attach line and column to its own errors.
    """
    parser = expat.ParserCreate()
    parser.StartElementHandler = handler.start
    parser.EndElementHandler = handler.end
    position_sink.append(_ExpatPosition(parser))
    try:
        while chunk := stream.read(CHUNK_SIZE):
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except Stop:
        return
    except expat.ExpatError as exc:
        raise ParseError(
            expat.ErrorString(exc.code) if exc.code else str(exc),
            line=exc.lineno,
            column=exc.offset + 1,
        ) from None
