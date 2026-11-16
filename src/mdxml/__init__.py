"""Fast, zero-dependency, streaming parser for FMI modelDescription.xml files."""

from __future__ import annotations

from mdxml._cli import main
from mdxml._dict import to_dict
from mdxml._errors import MdxmlError, ParseError, UnsupportedFmiVersion
from mdxml._header import read_header
from mdxml._source import Source

__all__ = [
    "MdxmlError",
    "ParseError",
    "Source",
    "UnsupportedFmiVersion",
    "main",
    "read_header",
    "to_dict",
]
