"""The FMI 2.0 Model Header."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from mdxml import _convert
from mdxml._errors import ParseError


class VariableNamingConvention(str, Enum):
    """``variableNamingConvention`` on ``fmiModelDescription``."""

    FLAT = "flat"
    STRUCTURED = "structured"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelHeader:
    """Everything in an FMI 2.0 Model Description before ``ModelVariables``.

    For now only the root ``fmiModelDescription`` attributes are parsed.
    """

    fmi_version: str
    model_name: str
    guid: str
    description: str | None = None
    author: str | None = None
    version: str | None = None
    copyright: str | None = None
    license: str | None = None
    generation_tool: str | None = None
    generation_date_and_time: datetime | None = None
    variable_naming_convention: VariableNamingConvention | str = VariableNamingConvention.FLAT
    number_of_event_indicators: int | None = None


def _text(value: str) -> str:
    return value


def _naming(value: str) -> VariableNamingConvention | str:
    return _convert.to_enum(VariableNamingConvention, value)


# XSD attribute name -> (field name, converter). Attributes not listed are ignored (lenient).
_ROOT_ATTRIBUTES: Mapping[str, tuple[str, Callable[[str], Any]]] = MappingProxyType({
    "fmiVersion": ("fmi_version", _text),
    "modelName": ("model_name", _text),
    "guid": ("guid", _text),
    "description": ("description", _text),
    "author": ("author", _text),
    "version": ("version", _text),
    "copyright": ("copyright", _text),
    "license": ("license", _text),
    "generationTool": ("generation_tool", _text),
    "generationDateAndTime": ("generation_date_and_time", _convert.to_datetime),
    "variableNamingConvention": ("variable_naming_convention", _naming),
    "numberOfEventIndicators": ("number_of_event_indicators", _convert.to_unsigned_int),
})

# Required by the XSD. Missing ones become "" in lenient mode (ADR 0003).
_REQUIRED_TEXT = ("model_name", "guid")


def build_header(attrs: dict[str, str], *, line: int, column: int) -> ModelHeader:
    """Build a :class:`ModelHeader` from the root element's attributes."""
    fields: dict[str, Any] = {}
    for xml_name, raw in attrs.items():
        spec = _ROOT_ATTRIBUTES.get(xml_name)
        if spec is None:
            continue
        field, convert = spec
        try:
            fields[field] = convert(raw)
        except ValueError as exc:
            raise ParseError(f"invalid {xml_name}={raw!r} on fmiModelDescription: {exc}", line=line, column=column) from None
    for field in _REQUIRED_TEXT:
        fields.setdefault(field, "")
    return ModelHeader(**fields)
