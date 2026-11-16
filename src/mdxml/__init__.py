"""Fast, zero-dependency, streaming parser for FMI modelDescription.xml files."""

from __future__ import annotations

from mdxml import fmi2, fmi3
from mdxml._cli import main
from mdxml._dict import to_dict
from mdxml._errors import MdxmlError, ParseError, UnsafeInput, UnsupportedFmiVersion
from mdxml._header import AnyModelHeader, read_header
from mdxml._lookup import Named
from mdxml._protocols import InterfaceType, ModelHeader, ModelVariable
from mdxml._read import AnyModelDescription, read
from mdxml._reader import DEFAULT_MAX_XML_BYTES
from mdxml._source import Source
from mdxml._variables import AnyVariable, VariableIterator, iter_variables

__all__ = [
    "DEFAULT_MAX_XML_BYTES",
    "AnyModelDescription",
    "AnyModelHeader",
    "AnyVariable",
    "InterfaceType",
    "MdxmlError",
    "ModelHeader",
    "ModelVariable",
    "Named",
    "ParseError",
    "Source",
    "UnsafeInput",
    "UnsupportedFmiVersion",
    "VariableIterator",
    "fmi2",
    "fmi3",
    "iter_variables",
    "main",
    "read",
    "read_header",
    "to_dict",
]
