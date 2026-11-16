"""Exceptions raised by mdxml."""

from __future__ import annotations


class MdxmlError(Exception):
    """Base class for every error mdxml raises on purpose."""


class ParseError(MdxmlError, ValueError):
    """The Model Description is malformed XML or holds a value that can't be read.

    ``line`` is 1-based and ``column`` is 1-based, pointing at where the
    parser was when the problem was found. Both are ``None`` when unknown.
    """

    def __init__(self, message: str, *, line: int | None = None, column: int | None = None) -> None:
        self.message = message
        self.line = line
        self.column = column
        location = f" (line {line}, column {column})" if line is not None and column is not None else ""
        super().__init__(f"{message}{location}")


class UnsupportedFmiVersion(MdxmlError):
    """The Model Description declares an FMI Version mdxml doesn't support."""

    def __init__(self, fmi_version: str, reason: str = "mdxml supports FMI 2.0 and 3.0") -> None:
        self.fmi_version = fmi_version
        super().__init__(f"unsupported FMI version {fmi_version!r}: {reason}")
