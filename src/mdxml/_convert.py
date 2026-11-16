"""Conversions from XSD attribute strings to Python values."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import TypeVar

E = TypeVar("E", bound=Enum)

_TRUE = frozenset({"true", "1"})
_FALSE = frozenset({"false", "0"})
_UTC_SUFFIX = re.compile(r"[Zz]$")


def to_bool(text: str) -> bool:
    """``xs:boolean``: ``true``/``false``/``1``/``0``, surrounding whitespace ignored."""
    value = text.strip()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"not an xs:boolean: {text!r}")


def to_int(text: str) -> int:
    """``xs:int`` and friends."""
    return int(text.strip())


def to_unsigned_int(text: str) -> int:
    """``xs:unsignedInt`` and friends: an int that must not be negative."""
    value = int(text.strip())
    if value < 0:
        raise ValueError(f"not an unsigned integer: {text!r}")
    return value


def to_datetime(text: str) -> datetime:
    """``xs:dateTime``. Accepts a trailing ``Z`` on every supported Python version."""
    return datetime.fromisoformat(_UTC_SUFFIX.sub("+00:00", text.strip()))


def to_enum(enum: type[E], text: str) -> E | str:
    """Convert a fixed-choice attribute. Values outside the allowed set stay plain strings (lenient)."""
    try:
        return enum(text.strip())
    except ValueError:
        return text
