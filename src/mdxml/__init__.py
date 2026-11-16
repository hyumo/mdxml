"""Fast, zero-dependency, streaming parser for FMI modelDescription.xml files."""

from __future__ import annotations

from mdxml import fmi2, fmi3
from mdxml._cli import main
from mdxml._dict import to_dict
from mdxml._errors import MdxmlError, ParseError, UnsafeInput, UnsupportedFmiVersion
from mdxml._header import read_header
from mdxml._reader import DEFAULT_MAX_XML_BYTES
from mdxml._source import Source

__all__ = [
    "DEFAULT_MAX_XML_BYTES",
    "MdxmlError",
    "ParseError",
    "Source",
    "UnsafeInput",
    "UnsupportedFmiVersion",
    "fmi2",
    "fmi3",
    "main",
    "read_header",
    "to_dict",
]
