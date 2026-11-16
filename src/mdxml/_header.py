"""Reading the Model Header: parse up to ``<ModelVariables>`` and stop."""

from __future__ import annotations

import os

from mdxml import _reader
from mdxml._errors import ParseError, UnsupportedFmiVersion
from mdxml.fmi2._header import ModelHeader as Fmi2ModelHeader
from mdxml.fmi2._header import build_header as build_fmi2_header

ROOT = "fmiModelDescription"


class _HeaderHandler:
    """Builds the Model Header from the root element, then stops at ``<ModelVariables>``."""

    __slots__ = ("_depth", "_position", "header")

    def __init__(self, position: list[_reader.Position]) -> None:
        self._depth = 0
        self._position = position
        self.header: Fmi2ModelHeader | None = None

    def _error(self, message: str) -> ParseError:
        pos = self._position[0]
        return ParseError(message, line=pos.line, column=pos.column)

    def start(self, name: str, attrs: dict[str, str]) -> None:
        self._depth += 1
        if self._depth == 1:
            self._start_root(name, attrs)
        elif self._depth == 2 and name == "ModelVariables":
            raise _reader.Stop

    def end(self, name: str) -> None:
        self._depth -= 1

    def _start_root(self, name: str, attrs: dict[str, str]) -> None:
        if name != ROOT:
            raise self._error(f"root element is <{name}>, expected <{ROOT}>")
        fmi_version = attrs.get("fmiVersion")
        if fmi_version is None:
            raise self._error(f"<{ROOT}> has no fmiVersion attribute")
        major = fmi_version.strip().split(".", 1)[0]
        if major == "2":
            pos = self._position[0]
            self.header = build_fmi2_header(attrs, line=pos.line, column=pos.column)
        elif major == "3":
            raise UnsupportedFmiVersion(fmi_version, "FMI 3 support is not implemented yet")
        else:
            raise UnsupportedFmiVersion(fmi_version)


def read_header(src: str | os.PathLike[str]) -> Fmi2ModelHeader:
    """Read the Model Header from a ``modelDescription.xml`` file.

    Parsing stops at ``<ModelVariables>``, so the cost doesn't depend on how
    many Model Variables the FMU has.
    """
    position: list[_reader.Position] = []
    handler = _HeaderHandler(position)
    with open(src, "rb") as stream:
        _reader.run(stream, handler, position)
    if handler.header is None:  # pragma: no cover - expat rejects documents without a root
        raise ParseError(f"no <{ROOT}> element found")
    return handler.header
