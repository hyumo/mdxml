"""Conversions from XSD attribute strings to Python values.

Every converter has the same shape, ``convert(text, *, strict) -> value``, and
raises :class:`ValueError` when ``text`` isn't a valid value. ``strict`` only
matters where lenient mode accepts more than the XSD does (ADR 0003).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Protocol, TypeVar

E = TypeVar("E", bound=Enum)
T_co = TypeVar("T_co", covariant=True)

_TRUE = frozenset({"true", "1"})
_FALSE = frozenset({"false", "0"})
_UTC_SUFFIX = re.compile(r"[Zz]$")
# xs:double's lexical space; float() alone would also accept "1_000" and "infinity".
_DOUBLE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?|[+-]?INF|NaN")
_INTEGER = re.compile(r"[+-]?\d+")


class Converter(Protocol[T_co]):
    """Turns an attribute's text into a Python value."""

    def __call__(self, text: str, /, *, strict: bool) -> T_co: ...


def to_text(text: str, *, strict: bool) -> str:
    """``xs:string`` and ``xs:normalizedString``: kept exactly as written."""
    return text


def to_bool(text: str, *, strict: bool) -> bool:
    """``xs:boolean``: ``true``/``false``/``1``/``0``. Lenient mode also ignores case (``True``, ``FALSE``)."""
    value = text.strip()
    if not strict:
        value = value.lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"not an xs:boolean: {text!r}")


def to_int(text: str, *, strict: bool) -> int:
    """``xs:int`` and friends."""
    value = text.strip()
    if not _INTEGER.fullmatch(value):
        raise ValueError(f"not an integer: {text!r}")
    return int(value)


def to_unsigned_int(text: str, *, strict: bool) -> int:
    """``xs:unsignedInt`` and friends: an integer that must not be negative."""
    value = to_int(text, strict=strict)
    if value < 0:
        raise ValueError(f"not an unsigned integer: {text!r}")
    return value


class IntRange(Converter[int]):
    """An XSD integer type with bounds, e.g. ``xs:byte`` is ``IntRange(-128, 127)``."""

    __slots__ = ("_high", "_low", "_name")

    def __init__(self, name: str, low: int, high: int) -> None:
        self._name = name
        self._low = low
        self._high = high

    def __call__(self, text: str, /, *, strict: bool) -> int:
        """Convert ``text``, checking it's within the type's bounds."""
        value = to_int(text, strict=strict)
        if not self._low <= value <= self._high:
            raise ValueError(f"{text!r} is out of range for {self._name} [{self._low}, {self._high}]")
        return value


BYTE = IntRange("xs:byte", -(2**7), 2**7 - 1)
UNSIGNED_BYTE = IntRange("xs:unsignedByte", 0, 2**8 - 1)
SHORT = IntRange("xs:short", -(2**15), 2**15 - 1)
UNSIGNED_SHORT = IntRange("xs:unsignedShort", 0, 2**16 - 1)
INT = IntRange("xs:int", -(2**31), 2**31 - 1)
UNSIGNED_INT = IntRange("xs:unsignedInt", 0, 2**32 - 1)
LONG = IntRange("xs:long", -(2**63), 2**63 - 1)
UNSIGNED_LONG = IntRange("xs:unsignedLong", 0, 2**64 - 1)


def to_double(text: str, *, strict: bool) -> float:
    """``xs:double``, including ``INF``, ``-INF`` and ``NaN``."""
    value = text.strip()
    if not _DOUBLE.fullmatch(value):
        raise ValueError(f"not an xs:double: {text!r}")
    return float(value)


def to_datetime(text: str, *, strict: bool) -> datetime:
    """``xs:dateTime``. Accepts a trailing ``Z`` on every supported Python version."""
    return datetime.fromisoformat(_UTC_SUFFIX.sub("+00:00", text.strip()))


class EnumConverter(Converter[E | str]):
    """A fixed-choice attribute. In lenient mode, values outside the allowed set stay plain strings."""

    __slots__ = ("_enum",)

    def __init__(self, enum: type[E]) -> None:
        self._enum = enum

    def __call__(self, text: str, /, *, strict: bool) -> E | str:
        """Convert ``text`` to a member of the enum."""
        try:
            return self._enum(text.strip())
        except ValueError:
            if strict:
                allowed = ", ".join(repr(member.value) for member in self._enum)
                raise ValueError(f"{text!r} is not one of {allowed}") from None
            return text
