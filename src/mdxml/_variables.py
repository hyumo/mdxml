"""Streaming Model Variables: one pass that builds the Model Header, then yields variables one at a time.

Expat pushes events while :func:`iter_variables` has to be pulled from, so the
iterator feeds expat one chunk at a time and hands out the variables that
chunk completed before reading the next one. Memory therefore stays bounded
by the chunk size, however many variables the FMU has. Parsing stops at
``</ModelVariables>``; the Model Structure is never read.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import ExitStack
from enum import Enum
from types import TracebackType
from typing import Any

from mdxml import _reader
from mdxml._errors import ParseError
from mdxml._grammar import Grammar, TreeHandler
from mdxml._header import AnyModelHeader, choose_header_grammar
from mdxml._schema import Frame
from mdxml._source import Source, open_source
from mdxml.fmi2 import _structure as fmi2_structure
from mdxml.fmi2 import _variables as fmi2_variables
from mdxml.fmi2._header import ModelHeader as Fmi2ModelHeader
from mdxml.fmi2._variables import Variable as Fmi2Variable
from mdxml.fmi3 import _structure as fmi3_structure
from mdxml.fmi3 import _variables as fmi3_variables
from mdxml.fmi3._variables import Variable as Fmi3Variable

AnyVariable = Fmi2Variable | Fmi3Variable
"""A Model Variable of any supported FMI Version."""

FilterValues = Callable[[str, Mapping[str, str]], tuple[str, str]]
"""Gives a variable's causality and variability from its element name and raw attributes."""

Selector = str | Iterable[str] | None
"""A filter value: one value, several, or ``None`` for no filtering."""

MODEL_VARIABLES = "ModelVariables"
MODEL_STRUCTURE = "ModelStructure"


def _selector(value: Selector) -> frozenset[str] | None:
    if value is None:
        return None
    values = [value] if isinstance(value, str) else list(value)
    # Enum members hash by name, not value, so compare on their string values.
    return frozenset(str(v.value) if isinstance(v, Enum) else str(v) for v in values)


class VariableFilter:
    """Decides from a variable's raw attributes whether to build it at all."""

    __slots__ = ("_causality", "_name_prefix", "_variability")

    def __init__(self, *, causality: Selector, variability: Selector, name_prefix: str | None) -> None:
        self._causality = _selector(causality)
        self._variability = _selector(variability)
        self._name_prefix = name_prefix

    @property
    def active(self) -> bool:
        return self._causality is not None or self._variability is not None or self._name_prefix is not None

    def matches(self, element: str, attrs: dict[str, str], values: FilterValues) -> bool:
        if self._name_prefix is not None and not attrs.get("name", "").startswith(self._name_prefix):
            return False
        if self._causality is None and self._variability is None:
            return True
        causality, variability = values(element, attrs)
        if self._causality is not None and causality not in self._causality:
            return False
        return self._variability is None or variability in self._variability


class _VariablesHandler:
    """Builds the Model Header, then each Model Variable as its element closes."""

    __slots__ = (
        "_after_model_structure",
        "_after_variables",
        "_filter",
        "_filter_values",
        "_grammars",
        "_header_handler",
        "_in_structure",
        "_in_variable",
        "_index",
        "_position",
        "_read_structure",
        "_skip_depth",
        "_strict",
        "_structure_handler",
        "_variable_handler",
        "done",
        "header",
        "model_structure",
        "pending",
    )

    def __init__(
        self,
        position: list[_reader.Position],
        *,
        strict: bool,
        variable_filter: VariableFilter,
        read_structure: bool = False,
    ) -> None:
        self._position = position
        self._read_structure = read_structure
        self._after_variables = False
        self._in_structure = False
        self._structure_handler: TreeHandler[Any] | None = None
        self._after_model_structure: frozenset[str] = frozenset()
        self.model_structure: Any = None
        self._strict = strict
        self._filter = variable_filter if variable_filter.active else None
        self._header_handler = TreeHandler(choose_header_grammar, position, strict=strict)
        self._variable_handler: TreeHandler[Any] | None = None
        self._grammars: Mapping[str, Grammar[Any]] = {}
        self._filter_values: FilterValues = fmi2_variables.filter_values
        self._in_variable = False
        self._index = 0
        self._skip_depth = 0
        self.header: AnyModelHeader | None = None
        self.pending: deque[AnyVariable] = deque()
        self.done = False

    def start(self, name: str, attrs: dict[str, str]) -> None:
        """Open an element."""
        if self.header is None:
            if name == MODEL_VARIABLES and self._header_handler.at_root_level:
                self.header = self._header_handler.stop_here()
                self._enter_model_variables(self.header)
            else:
                self._header_handler.start(name, attrs)
            return
        if self._skip_depth:
            self._skip_depth += 1
            return
        if self._after_variables:
            self._start_after_variables(name, attrs)
            return
        if self._in_variable:
            assert self._variable_handler is not None  # noqa: S101 - set on entering ModelVariables
            self._variable_handler.start(name, attrs)
            return
        # A direct child of <ModelVariables>.
        if name not in self._grammars:
            if self._strict:
                pos = self._position[0]
                raise ParseError(f"unknown element <{name}> in <{MODEL_VARIABLES}>", line=pos.line, column=pos.column)
            self._skip_depth = 1
            return
        self._index += 1
        if self._filter is not None and not self._filter.matches(name, attrs, self._filter_values):
            self._skip_depth = 1  # skipped variables are never turned into objects
            return
        assert self._variable_handler is not None  # noqa: S101 - set on entering ModelVariables
        self._in_variable = True
        self._variable_handler.reset()
        self._variable_handler.start(name, attrs)

    def end(self, name: str) -> None:
        """Close an element; a closing variable is built and queued."""
        if self.header is None:
            self._header_handler.end(name)
            return
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if self._after_variables:
            self._end_after_variables(name)
            return
        if self._in_variable:
            assert self._variable_handler is not None  # noqa: S101
            self._variable_handler.end(name)
            if self._variable_handler.result is not None:
                cls, fields = self._variable_handler.result
                self.pending.append(cls(index=self._index, **fields))
                self._in_variable = False
            return
        if self._read_structure:
            self._after_variables = True  # keep reading: the Model Structure comes next
            return
        # </ModelVariables>: nothing after it is needed.
        self.done = True
        raise _reader.Stop

    def _start_after_variables(self, name: str, attrs: dict[str, str]) -> None:
        """Open an element after ``</ModelVariables>``: only the Model Structure is built."""
        if self._in_structure:
            assert self._structure_handler is not None  # noqa: S101 - set on entering ModelVariables
            self._structure_handler.start(name, attrs)
            return
        # A direct child of the root.
        if name == MODEL_STRUCTURE and (self.model_structure is None or not self._strict):
            assert self._structure_handler is not None  # noqa: S101
            if self.model_structure is None:  # lenient: a second ModelStructure is ignored
                self._in_structure = True
                self._structure_handler.reset()
                self._structure_handler.start(name, attrs)
                return
        elif name in self._after_model_structure:
            pass  # e.g. FMI 3's trailing <Annotations>: skipped
        elif self._strict:
            pos = self._position[0]
            raise ParseError(f"unexpected element <{name}> after <{MODEL_VARIABLES}>", line=pos.line, column=pos.column)
        self._skip_depth = 1

    def _end_after_variables(self, name: str) -> None:
        """Close an element after ``</ModelVariables>``; the root closing ends the document."""
        if self._in_structure:
            assert self._structure_handler is not None  # noqa: S101
            self._structure_handler.end(name)
            if self._structure_handler.result is not None:
                self.model_structure = self._structure_handler.result
                self._in_structure = False
            return
        self.done = True
        raise _reader.Stop

    def finish(self) -> AnyModelHeader:
        """Return the Model Header once the document has ended without ``<ModelVariables>``."""
        if self.header is None:
            self.header = self._header_handler.finish()
        return self.header

    def _enter_model_variables(self, header: AnyModelHeader) -> None:
        structure_grammar: Grammar[Any]
        if isinstance(header, Fmi2ModelHeader):
            self._grammars = fmi2_variables.VARIABLE_GRAMMARS
            self._filter_values = fmi2_variables.filter_values
            structure_grammar = fmi2_structure.STRUCTURE_GRAMMAR
            self._after_model_structure = fmi2_structure.AFTER_MODEL_STRUCTURE
        else:
            self._grammars = fmi3_variables.VARIABLE_GRAMMARS
            self._filter_values = fmi3_variables.filter_values
            structure_grammar = fmi3_structure.STRUCTURE_GRAMMAR
            self._after_model_structure = fmi3_structure.AFTER_MODEL_STRUCTURE
        self._variable_handler = TreeHandler(self._choose_variable_grammar, self._position, strict=self._strict)
        if self._read_structure:
            self._structure_handler = TreeHandler(lambda _: structure_grammar, self._position, strict=self._strict)

    def _choose_variable_grammar(self, root: Frame) -> Grammar[Any]:
        return self._grammars[root.tag]


class VariableIterator:
    """Iterator over an FMU's Model Variables, read in a single streaming pass.

    :attr:`header` gives the Model Header from the same pass. The source is
    opened on first use and closed when iteration ends or fails; use the
    iterator in a ``with`` block (or call :meth:`close`) to close it early.
    """

    __slots__ = ("_handler", "_max_xml_bytes", "_member", "_position", "_resources", "_src", "_steps", "_strict")

    def __init__(
        self,
        src: Source,
        *,
        member: str | None,
        strict: bool,
        max_xml_bytes: int,
        variable_filter: VariableFilter,
        read_structure: bool = False,
    ) -> None:
        """Prepare the iterator; nothing is read until it's used."""
        self._src = src
        self._member = member
        self._strict = strict
        self._max_xml_bytes = max_xml_bytes
        self._position: list[_reader.Position] = []
        self._handler = _VariablesHandler(
            self._position, strict=strict, variable_filter=variable_filter, read_structure=read_structure
        )
        self._resources = ExitStack()
        self._steps: Generator[None, None, None] | None = None

    def __iter__(self) -> VariableIterator:
        """Return the iterator itself."""
        return self

    def __next__(self) -> AnyVariable:
        """Return the next Model Variable."""
        pending = self._handler.pending
        # The last chunk can both finish the document and queue variables, so only stop when
        # there's nothing left to read *and* nothing queued.
        while not pending:
            if not self._advance() and not pending:
                raise StopIteration
        return pending.popleft()

    @property
    def header(self) -> AnyModelHeader:
        """The Model Header, read (if it hasn't been yet) without consuming any variables."""
        while self._handler.header is None and self._advance():
            pass
        return self._handler.finish()

    @property
    def model_structure(self) -> Any:
        """The Model Structure, once iteration has finished (only when created by :func:`mdxml.read`)."""
        return self._handler.model_structure

    def close(self) -> None:
        """Stop reading and close the source."""
        self._resources.close()
        if self._steps is not None:
            self._steps.close()

    def __enter__(self) -> VariableIterator:
        """Use the iterator as a context manager that closes the source on exit."""
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        """Close the source."""
        self.close()

    def _advance(self) -> bool:
        """Parse one more chunk. Return ``False`` once there's nothing left to read."""
        if self._handler.done:
            self.close()
            return False
        try:
            if self._steps is None:
                stream = self._resources.enter_context(open_source(self._src, self._member, self._max_xml_bytes))
                self._steps = _reader.feed(stream, self._handler, self._position, max_xml_bytes=self._max_xml_bytes)
            next(self._steps)
        except StopIteration:
            self.close()
            self._handler.finish()
            return False
        except BaseException:
            self.close()
            raise
        return True


def iter_variables(
    src: Source,
    *,
    causality: Selector = None,
    variability: Selector = None,
    name_prefix: str | None = None,
    member: str | None = None,
    strict: bool = False,
    max_xml_bytes: int = _reader.DEFAULT_MAX_XML_BYTES,
) -> VariableIterator:
    """Stream an FMU's Model Variables one at a time, in file order.

    ``src``, ``member``, ``strict`` and ``max_xml_bytes`` work as for
    :func:`mdxml.read_header`. Memory use doesn't grow with the number of
    variables, and nothing after ``</ModelVariables>`` is read.

    ``causality`` and ``variability`` (one value or several) and
    ``name_prefix`` keep only matching variables. They're checked against the
    raw attributes before a variable is built, so skipped variables cost
    almost nothing; Variable Indexes still count every variable.

    The returned iterator's ``.header`` is the Model Header from the same pass.
    """
    _reader.check_max_xml_bytes(max_xml_bytes)
    if isinstance(src, (str, os.PathLike)) and not os.path.exists(src):
        raise FileNotFoundError(f"no such file or directory: {os.fspath(src)!r}")
    variable_filter = VariableFilter(causality=causality, variability=variability, name_prefix=name_prefix)
    return VariableIterator(
        src, member=member, strict=strict, max_xml_bytes=max_xml_bytes, variable_filter=variable_filter
    )
