"""Turning expat events into parsed objects with a per-version grammar.

A :class:`Grammar` says which child elements each element may contain and how
to build each one. :class:`TreeHandler` keeps a stack of open elements, builds
each element from its attributes and already-built children when it closes,
and stops when the root's ``stop_at`` child opens. Unknown elements are
skipped with their whole subtree, or raise with ``strict=True``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar

from mdxml import _reader
from mdxml._errors import ParseError
from mdxml._schema import EMPTY, Frame, attributes

R = TypeVar("R")
R_co = TypeVar("R_co", covariant=True)


class Builder(Protocol[R_co]):
    """Builds one element's object from its frame (attributes and built children)."""

    def __call__(self, frame: Frame, /, *, strict: bool) -> R_co: ...


class _Skip:
    __slots__ = ()

    def __repr__(self) -> str:
        return "SKIP"


SKIP = _Skip()
"""Marks a known child element whose subtree is deliberately not parsed (e.g. annotations)."""


class RawBuilder(Protocol[R_co]):
    """Builds an element from its frame (attributes only) and its raw inner XML."""

    def __call__(self, frame: Frame, xml: str, /, *, strict: bool) -> R_co: ...


class Raw:
    """Marks a child element kept as raw XML: its attributes are parsed, its content is not.

    The content is the document's original bytes between the start and end tags,
    decoded as UTF-8 (which FMI requires), so it can be parsed again later.
    """

    __slots__ = ("build",)

    def __init__(self, build: RawBuilder[object]) -> None:
        self.build = build


ChildRule = Builder[object] | _Skip | Raw


_QUOTES = (ord('"'), ord("'"))
_TAG_END = ord(">")


def _start_tag_length(data: bytes) -> int:
    """Return the length of the start tag at the beginning of ``data``, up to and including its ``>``."""
    quote = 0
    for i, byte in enumerate(data):
        if quote:
            if byte == quote:
                quote = 0
        elif byte in _QUOTES:
            quote = byte
        elif byte == _TAG_END:
            return i + 1
    raise ParseError("start tag isn't complete")  # pragma: no cover - expat reports a start tag only once it's whole


class Collect:
    """Builder for a list element: no attributes of its own, returns its children in document order.

    With a ``tag``, only children with that tag; without one, all of them.
    """

    __slots__ = ("_tag",)

    def __init__(self, tag: str | None = None) -> None:
        self._tag = tag

    def __call__(self, frame: Frame, /, *, strict: bool) -> tuple[object, ...]:
        """Return the built children."""
        attributes(frame, EMPTY, strict=strict)
        if self._tag is None:
            return tuple(obj for _, obj in frame.children)
        return tuple(frame.all(self._tag))


@dataclass(frozen=True, slots=True)
class Grammar(Generic[R_co]):
    """The elements of one document part, e.g. the FMI 2 Model Header."""

    root: str
    stop_at: str
    build_root: Builder[R_co]
    children: Mapping[str, Mapping[str, ChildRule]]

    def __post_init__(self) -> None:
        frozen = {parent: MappingProxyType(dict(rules)) for parent, rules in self.children.items()}
        object.__setattr__(self, "children", MappingProxyType(frozen))


class TreeHandler(Generic[R]):
    """Expat handler that builds the root object of a :class:`Grammar`."""

    __slots__ = (
        "_choose",
        "_grammar",
        "_position",
        "_raw",
        "_raw_depth",
        "_skip_depth",
        "_stack",
        "_strict",
        "result",
        "stopped",
    )

    def __init__(
        self,
        choose_grammar: Callable[[Frame], Grammar[R]],
        position: list[_reader.Position],
        *,
        strict: bool,
    ) -> None:
        """Create a handler; ``choose_grammar`` picks the grammar from the root frame (e.g. by FMI Version)."""
        self._choose = choose_grammar
        self._grammar: Grammar[R] | None = None
        self._position = position
        self._strict = strict
        self._stack: list[Frame] = []
        self._skip_depth = 0
        self._raw: tuple[Frame, Raw, int, bool] | None = None
        """While a :class:`Raw` element is open: its frame, rule, content start and whether it's empty."""
        self._raw_depth = 0
        self.result: R | None = None
        self.stopped = False

    @property
    def at_root_level(self) -> bool:
        """Return whether the next element to open would be a direct child of the root."""
        return self._grammar is not None and not self._skip_depth and len(self._stack) == 1

    def stop_here(self) -> R:
        """Build the root object from what has been read so far, as if ``stop_at`` had opened."""
        self.stopped = True
        return self.finish()

    def reset(self) -> None:
        """Forget everything read so far, to build another root; the grammar is chosen again for it."""
        self._grammar = None
        self._stack.clear()
        self._skip_depth = 0
        if self._raw is not None:
            self._position[0].release()
        self._raw = None
        self._raw_depth = 0
        self.result = None
        self.stopped = False

    def start(self, name: str, attrs: dict[str, str]) -> None:
        """Open an element."""
        if self._skip_depth:
            self._skip_depth += 1
            return
        if self._raw_depth:
            self._raw_depth += 1
            return
        pos = self._position[0]
        frame = Frame(name, attrs, pos.line, pos.column)
        if not self._stack:
            if self._grammar is None:
                self._grammar = self._choose(frame)
            self._stack.append(frame)
            return
        assert self._grammar is not None  # noqa: S101 - set when the root opened
        parent = self._stack[-1]
        if len(self._stack) == 1 and name == self._grammar.stop_at:
            self.stopped = True
            raise _reader.Stop
        rule = self._grammar.children.get(parent.tag, {}).get(name)
        if rule is None:
            if self._strict:
                raise frame.error(f"unknown element <{name}> in <{parent.tag}>")
            self._skip_depth = 1
            return
        if isinstance(rule, _Skip):
            self._skip_depth = 1
            return
        if isinstance(rule, Raw):
            self._start_raw(frame, rule)
            return
        self._stack.append(frame)

    def _start_raw(self, frame: Frame, rule: Raw) -> None:
        pos = self._position[0]
        start = pos.byte_index
        pos.keep_from(start)
        tag_length = _start_tag_length(pos.kept(start, sys.maxsize))
        self_closing = pos.kept(start + tag_length - 2, start + tag_length) == b"/>"
        self._raw = (frame, rule, start + tag_length, self_closing)
        self._raw_depth = 1

    def _end_raw(self) -> None:
        assert self._raw is not None  # noqa: S101 - only called while a Raw element is open
        frame, rule, content_start, self_closing = self._raw
        pos = self._position[0]
        content = b"" if self_closing else pos.kept(content_start, pos.byte_index)
        pos.release()
        self._raw = None
        try:
            xml = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise frame.error(f"<{frame.tag}> content isn't valid UTF-8: {exc}") from None
        self._stack[-1].children.append((frame.tag, rule.build(frame, xml, strict=self._strict)))

    def end(self, name: str) -> None:
        """Close an element and build its object."""
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if self._raw_depth:
            self._raw_depth -= 1
            if not self._raw_depth:
                self._end_raw()
            return
        assert self._grammar is not None  # noqa: S101 - start() always sets it first
        frame = self._stack.pop()
        if not self._stack:
            self.result = self._grammar.build_root(frame, strict=self._strict)
            return
        parent = self._stack[-1]
        rule = self._grammar.children[parent.tag][frame.tag]
        assert not isinstance(rule, _Skip | Raw)  # noqa: S101 - skipped and raw elements never get a frame
        parent.children.append((frame.tag, rule(frame, strict=self._strict)))

    def finish(self) -> R:
        """Return the root object once parsing has stopped or the document has ended."""
        if self.result is not None:
            if self._strict and self._grammar is not None and not self.stopped:
                raise ParseError(f"<{self._grammar.root}> has no <{self._grammar.stop_at}> element")
            return self.result
        if self._grammar is None or len(self._stack) != 1:  # pragma: no cover - expat guarantees a closed root
            raise ParseError("document ended without a complete root element")
        self.result = self._grammar.build_root(self._stack[0], strict=self._strict)
        return self.result
