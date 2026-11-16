"""Building parsed objects from elements, following the XSD.

Each element type has an attribute table (:class:`Attr` entries keyed by XML
name) that says which field each attribute fills, how to convert it and
whether it's required. :func:`attributes` applies a table to one element,
following ADR 0003:

- unknown attributes are ignored, or raise with ``strict=True``;
- a missing optional attribute leaves the field at its XSD default;
- a missing required attribute raises with ``strict=True``; in lenient mode it
  takes the table's fallback if there is one (e.g. ``""`` for text), else raises;
- a value that can't be converted raises if the attribute is required or
  ``strict=True``; otherwise it's dropped and the field keeps its default.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from mdxml._convert import Converter, to_bool, to_double, to_text
from mdxml._errors import ParseError


class _NoFallback:
    __slots__ = ()

    def __repr__(self) -> str:
        return "NO_FALLBACK"


NO_FALLBACK: Any = _NoFallback()


@dataclass(frozen=True, slots=True)
class Attr:
    """How one XSD attribute maps onto a dataclass field."""

    xml: str
    field: str
    convert: Converter[object]
    required: bool = False
    fallback: object = NO_FALLBACK
    """Value used in lenient mode when a required attribute is missing."""


AttrTable = Mapping[str, Attr]


def table(*attrs: Attr) -> AttrTable:
    """Build a read-only attribute table keyed by XML name."""
    return MappingProxyType({attr.xml: attr for attr in attrs})


def required_text(xml: str, field: str) -> Attr:
    """Return a required text attribute; lenient mode uses ``""`` when it's missing."""
    return Attr(xml, field, to_text, required=True, fallback="")


def text(xml: str, field: str) -> Attr:
    """Return an optional text attribute."""
    return Attr(xml, field, to_text)


def flag(xml: str, field: str) -> Attr:
    """Return an optional ``xs:boolean`` attribute."""
    return Attr(xml, field, to_bool)


def double(xml: str, field: str) -> Attr:
    """Return an optional ``xs:double`` (or ``xs:float``) attribute."""
    return Attr(xml, field, to_double)


EMPTY = table()
"""The attribute table of an element without attributes."""


class Frame:
    """One open element while its subtree is being read."""

    __slots__ = ("attrs", "children", "column", "line", "tag")

    def __init__(self, tag: str, attrs: dict[str, str], line: int, column: int) -> None:
        self.tag = tag
        self.attrs = attrs
        self.line = line
        self.column = column
        self.children: list[tuple[str, object]] = []

    def error(self, message: str) -> ParseError:
        """Build a :class:`ParseError` pointing at this element."""
        return ParseError(message, line=self.line, column=self.column)

    def all(self, tag: str) -> list[Any]:
        """Return the built children with this tag, in document order."""
        return [obj for child_tag, obj in self.children if child_tag == tag]

    def one(self, tag: str, *, strict: bool) -> Any:
        """Return the single built child with this tag, or ``None``.

        More than one raises with ``strict=True``; lenient mode keeps the first.
        """
        found = self.all(tag)
        if len(found) > 1 and strict:
            raise self.error(f"<{self.tag}> has {len(found)} <{tag}> elements, expected at most one")
        return found[0] if found else None


def attributes(frame: Frame, spec: AttrTable, *, strict: bool) -> dict[str, Any]:
    """Convert ``frame``'s attributes into dataclass keyword arguments using ``spec``."""
    fields: dict[str, Any] = {}
    for xml_name, raw in frame.attrs.items():
        attr = spec.get(xml_name)
        if attr is None:
            if strict:
                raise frame.error(f"unknown attribute {xml_name!r} on <{frame.tag}>")
            continue
        try:
            fields[attr.field] = attr.convert(raw, strict=strict)
        except ValueError as exc:
            if strict or attr.required:
                raise frame.error(f"invalid {xml_name}={raw!r} on <{frame.tag}>: {exc}") from None
    for attr in spec.values():
        if attr.required and attr.field not in fields:
            if strict or attr.fallback is NO_FALLBACK:
                raise frame.error(f"<{frame.tag}> is missing required attribute {attr.xml!r}")
            fields[attr.field] = attr.fallback
    return fields
