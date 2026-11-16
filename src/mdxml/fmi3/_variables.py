"""FMI 3.0 Model Variables: the typed variable elements in ``ModelVariables``.

Each element kind (``Float64``, ``Int8``, ``Binary``, ``Clock``, …) has its
own class; ``type_name`` is the element name. Every variable also gets its
Variable Index: its 1-based position in ``ModelVariables``.

A variable with ``<Dimension>`` children is an array: its ``start`` is a
tuple of values, in row-major order. A scalar's ``start`` is a single value.
``String`` and ``Binary`` start values come from ``<Start value="…">``
children; ``Binary`` values are converted from hex to ``bytes``.

The XSD gives ``variability`` no default; the FMI 3.0 standard defines it
from causality and type, and that default is applied here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from mdxml import _convert as c
from mdxml._grammar import SKIP, Builder, ChildRule, Grammar
from mdxml._schema import Attr, AttrTable, Frame, attributes, double, flag, required_text, table, text
from mdxml.fmi3._header import IntervalVariability

# --- Enums ----------------------------------------------------------------------------------


class Causality(str, Enum):
    """``causality`` of a variable."""

    STRUCTURAL_PARAMETER = "structuralParameter"
    PARAMETER = "parameter"
    CALCULATED_PARAMETER = "calculatedParameter"
    INPUT = "input"
    OUTPUT = "output"
    LOCAL = "local"
    INDEPENDENT = "independent"


class Variability(str, Enum):
    """``variability`` of a variable."""

    CONSTANT = "constant"
    FIXED = "fixed"
    TUNABLE = "tunable"
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"


class Initial(str, Enum):
    """``initial`` of a variable."""

    EXACT = "exact"
    APPROX = "approx"
    CALCULATED = "calculated"


_PARAMETERS = frozenset({"parameter", "structuralParameter", "calculatedParameter"})
_FLOAT_ELEMENTS = frozenset({"Float32", "Float64"})


def default_variability(element: str, causality: str) -> Variability:
    """Return the FMI 3.0 standard's default ``variability`` for a variable element and causality.

    Parameters default to ``fixed``; otherwise ``Float32``/``Float64`` default to
    ``continuous`` and every other type (including clocks) to ``discrete``.
    """
    if causality in _PARAMETERS:
        return Variability.FIXED
    return Variability.CONTINUOUS if element in _FLOAT_ELEMENTS else Variability.DISCRETE


# Table 22 of the FMI 3.0.2 standard: the default `initial` (the underlined value) for each
# valid combination of causality and variability. Combinations not listed have no default:
# either `initial` isn't allowed (the independent variable) or the combination is invalid.
_DEFAULT_INITIAL: Mapping[tuple[Causality, Variability], Initial] = MappingProxyType(
    {
        (Causality.OUTPUT, Variability.CONSTANT): Initial.EXACT,
        (Causality.LOCAL, Variability.CONSTANT): Initial.EXACT,
        (Causality.STRUCTURAL_PARAMETER, Variability.FIXED): Initial.EXACT,
        (Causality.STRUCTURAL_PARAMETER, Variability.TUNABLE): Initial.EXACT,
        (Causality.PARAMETER, Variability.FIXED): Initial.EXACT,
        (Causality.PARAMETER, Variability.TUNABLE): Initial.EXACT,
        (Causality.CALCULATED_PARAMETER, Variability.FIXED): Initial.CALCULATED,
        (Causality.CALCULATED_PARAMETER, Variability.TUNABLE): Initial.CALCULATED,
        (Causality.LOCAL, Variability.FIXED): Initial.CALCULATED,
        (Causality.LOCAL, Variability.TUNABLE): Initial.CALCULATED,
        (Causality.INPUT, Variability.DISCRETE): Initial.EXACT,
        (Causality.INPUT, Variability.CONTINUOUS): Initial.EXACT,
        (Causality.OUTPUT, Variability.DISCRETE): Initial.CALCULATED,
        (Causality.OUTPUT, Variability.CONTINUOUS): Initial.CALCULATED,
        (Causality.LOCAL, Variability.DISCRETE): Initial.CALCULATED,
        (Causality.LOCAL, Variability.CONTINUOUS): Initial.CALCULATED,
    }
)


def default_initial(causality: Causality | str, variability: Variability | str) -> Initial | None:
    """Return the FMI 3.0 standard's default ``initial`` for a causality and variability.

    ``None`` when ``initial`` isn't allowed for the combination, when the
    combination is invalid, or when either value isn't a known enum value.
    """
    if not isinstance(causality, Causality) or not isinstance(variability, Variability):
        return None
    return _DEFAULT_INITIAL.get((causality, variability))


# --- Parts of variables ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Dimension:
    """One dimension of an array variable: a fixed ``start`` size, or the value reference of its size."""

    start: int | None = None
    value_reference: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Alias:
    """Another name for a variable. ``display_unit`` is only allowed on aliases of float variables."""

    name: str
    description: str | None = None
    display_unit: str | None = None


# --- Variables ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class AbstractVariable:
    """Attributes every FMI 3.0 Model Variable has, whatever its kind."""

    name: str
    value_reference: int
    index: int
    """The Variable Index: 1-based position in ``ModelVariables``."""
    variability: Variability | str
    """As written, or else the standard's default for this type and causality."""
    description: str | None = None
    causality: Causality | str = Causality.LOCAL
    can_handle_multiple_set_per_time_instant: bool | None = None
    clocks: tuple[int, ...] | None = None
    """Value references of the clocks this variable belongs to."""
    declared_type: str | None = None
    aliases: tuple[Alias, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ArrayableVariable(AbstractVariable):
    """A variable that can be an array and has ``initial``: every kind except ``Clock``."""

    initial: Initial | str | None = None
    """``initial`` exactly as written; see :attr:`effective_initial`."""
    dimensions: tuple[Dimension, ...] = ()
    """Empty for a scalar."""
    intermediate_update: bool | None = None
    previous: int | None = None

    @property
    def is_array(self) -> bool:
        """Whether the variable has ``<Dimension>`` elements."""
        return bool(self.dimensions)

    @property
    def effective_initial(self) -> Initial | str | None:
        """``initial`` as written, or else the standard's default for this causality and variability."""
        if self.initial is not None:
            return self.initial
        return default_initial(self.causality, self.variability)


@dataclass(frozen=True, slots=True, kw_only=True)
class _FloatVariable(ArrayableVariable):
    quantity: str | None = None
    unit: str | None = None
    display_unit: str | None = None
    relative_quantity: bool = False
    unbounded: bool = False
    min: float | None = None
    max: float | None = None
    nominal: float | None = None
    start: float | tuple[float, ...] | None = None
    derivative: int | None = None
    """Value reference of the state this variable is the derivative of."""
    reinit: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Float32Variable(_FloatVariable):
    """A ``Float32`` variable."""

    type_name: str = field(default="Float32", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Float64Variable(_FloatVariable):
    """A ``Float64`` variable."""

    type_name: str = field(default="Float64", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class _IntegerVariable(ArrayableVariable):
    quantity: str | None = None
    min: int | None = None
    max: int | None = None
    start: int | tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Int8Variable(_IntegerVariable):
    """An ``Int8`` variable."""

    type_name: str = field(default="Int8", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt8Variable(_IntegerVariable):
    """A ``UInt8`` variable."""

    type_name: str = field(default="UInt8", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Int16Variable(_IntegerVariable):
    """An ``Int16`` variable."""

    type_name: str = field(default="Int16", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt16Variable(_IntegerVariable):
    """A ``UInt16`` variable."""

    type_name: str = field(default="UInt16", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Int32Variable(_IntegerVariable):
    """An ``Int32`` variable."""

    type_name: str = field(default="Int32", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt32Variable(_IntegerVariable):
    """A ``UInt32`` variable."""

    type_name: str = field(default="UInt32", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Int64Variable(_IntegerVariable):
    """An ``Int64`` variable."""

    type_name: str = field(default="Int64", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt64Variable(_IntegerVariable):
    """A ``UInt64`` variable."""

    type_name: str = field(default="UInt64", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class BooleanVariable(ArrayableVariable):
    """A ``Boolean`` variable."""

    type_name: str = field(default="Boolean", init=False)
    start: bool | tuple[bool, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StringVariable(ArrayableVariable):
    """A ``String`` variable. Start values come from ``<Start>`` children."""

    type_name: str = field(default="String", init=False)
    start: str | tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BinaryVariable(ArrayableVariable):
    """A ``Binary`` variable. Start values come from ``<Start>`` children, as ``bytes``."""

    type_name: str = field(default="Binary", init=False)
    mime_type: str = "application/octet-stream"
    max_size: int | None = None
    start: bytes | tuple[bytes, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EnumerationVariable(ArrayableVariable):
    """An ``Enumeration`` variable. ``declared_type`` names its EnumerationType."""

    type_name: str = field(default="Enumeration", init=False)
    quantity: str | None = None
    min: int | None = None
    max: int | None = None
    start: int | tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ClockVariable(AbstractVariable):
    """A ``Clock`` variable. Clocks are never arrays and have no ``initial`` or ``start``."""

    type_name: str = field(default="Clock", init=False)
    interval_variability: IntervalVariability | str
    can_be_deactivated: bool = False
    priority: int | None = None
    interval_decimal: float | None = None
    shift_decimal: float = 0.0
    supports_fraction: bool = False
    resolution: int | None = None
    interval_counter: int | None = None
    shift_counter: int = 0


Variable = (
    Float32Variable
    | Float64Variable
    | Int8Variable
    | UInt8Variable
    | Int16Variable
    | UInt16Variable
    | Int32Variable
    | UInt32Variable
    | Int64Variable
    | UInt64Variable
    | BooleanVariable
    | StringVariable
    | BinaryVariable
    | EnumerationVariable
    | ClockVariable
)
"""Any FMI 3.0 Model Variable."""


# --- Attribute tables -----------------------------------------------------------------------

_ABSTRACT_ATTRS = (
    required_text("name", "name"),
    Attr("valueReference", "value_reference", c.UNSIGNED_INT, required=True),
    text("description", "description"),
    Attr("causality", "causality", c.EnumConverter(Causality)),
    Attr("variability", "variability", c.EnumConverter(Variability)),
    flag("canHandleMultipleSetPerTimeInstant", "can_handle_multiple_set_per_time_instant"),
    Attr("clocks", "clocks", c.ListOf(c.UNSIGNED_INT)),
    text("declaredType", "declared_type"),
)

_ARRAYABLE_ATTRS = (
    *_ABSTRACT_ATTRS,
    Attr("initial", "initial", c.EnumConverter(Initial)),
    flag("intermediateUpdate", "intermediate_update"),
    Attr("previous", "previous", c.UNSIGNED_INT),
)


def _float_attrs() -> AttrTable:
    return table(
        *_ARRAYABLE_ATTRS,
        text("quantity", "quantity"),
        text("unit", "unit"),
        text("displayUnit", "display_unit"),
        flag("relativeQuantity", "relative_quantity"),
        flag("unbounded", "unbounded"),
        double("min", "min"),
        double("max", "max"),
        double("nominal", "nominal"),
        Attr("start", "start", c.ListOf(c.to_double)),
        Attr("derivative", "derivative", c.UNSIGNED_INT),
        flag("reinit", "reinit"),
    )


def _integer_attrs(bounds: c.IntRange) -> AttrTable:
    return table(
        *_ARRAYABLE_ATTRS,
        text("quantity", "quantity"),
        Attr("min", "min", bounds),
        Attr("max", "max", bounds),
        Attr("start", "start", c.ListOf(bounds)),
    )


BOOLEAN_ATTRS = table(*_ARRAYABLE_ATTRS, Attr("start", "start", c.ListOf(c.to_bool)))

STRING_ATTRS = table(*_ARRAYABLE_ATTRS)

BINARY_ATTRS = table(
    *_ARRAYABLE_ATTRS,
    text("mimeType", "mime_type"),
    Attr("maxSize", "max_size", c.to_unsigned_int),  # xs:nonNegativeInteger has no upper bound
)

ENUMERATION_ATTRS = table(
    *(a for a in _ARRAYABLE_ATTRS if a.xml != "declaredType"),
    required_text("declaredType", "declared_type"),
    text("quantity", "quantity"),
    Attr("min", "min", c.LONG),
    Attr("max", "max", c.LONG),
    Attr("start", "start", c.ListOf(c.LONG)),
)

CLOCK_ATTRS = table(
    *_ABSTRACT_ATTRS,
    flag("canBeDeactivated", "can_be_deactivated"),
    Attr("priority", "priority", c.UNSIGNED_INT),
    Attr("intervalVariability", "interval_variability", c.EnumConverter(IntervalVariability), required=True),
    double("intervalDecimal", "interval_decimal"),
    double("shiftDecimal", "shift_decimal"),
    flag("supportsFraction", "supports_fraction"),
    Attr("resolution", "resolution", c.UNSIGNED_LONG),
    Attr("intervalCounter", "interval_counter", c.UNSIGNED_LONG),
    Attr("shiftCounter", "shift_counter", c.UNSIGNED_LONG),
)

DIMENSION_ATTRS = table(
    Attr("start", "start", c.UNSIGNED_LONG),
    Attr("valueReference", "value_reference", c.UNSIGNED_INT),
)

ALIAS_ATTRS = table(required_text("name", "name"), text("description", "description"))

FLOAT_ALIAS_ATTRS = table(
    required_text("name", "name"), text("description", "description"), text("displayUnit", "display_unit")
)

STRING_START_ATTRS = table(text("value", "value"))

BINARY_START_ATTRS = table(Attr("value", "value", c.to_hex_binary))

VariableFields = tuple[type[AbstractVariable], dict[str, Any]]
"""A variable's class and constructor arguments, everything but its Variable Index."""


# --- Builders -------------------------------------------------------------------------------


class _Part(Builder[object]):
    """Builds a part of a variable (``Dimension``, ``Alias``) from its attributes."""

    __slots__ = ("_attrs", "_cls")

    def __init__(self, cls: type[object], attrs: AttrTable) -> None:
        self._cls = cls
        self._attrs = attrs

    def __call__(self, frame: Frame, /, *, strict: bool) -> object:
        """Build the part."""
        return self._cls(**attributes(frame, self._attrs, strict=strict))


class _StartValue(Builder[object]):
    """Builds a ``<Start value="…">`` child of a String or Binary variable into its value."""

    __slots__ = ("_attrs",)

    def __init__(self, attrs: AttrTable) -> None:
        self._attrs = attrs

    def __call__(self, frame: Frame, /, *, strict: bool) -> object:
        """Return the start value; a missing ``value`` is the empty string or empty bytes."""
        fields = attributes(frame, self._attrs, strict=strict)
        return fields.get("value", b"" if self._attrs is BINARY_START_ATTRS else "")


def _shape_start(frame: Frame, values: tuple[Any, ...], *, is_array: bool, strict: bool) -> Any:
    """Return a scalar's start as one value and an array's as a tuple."""
    if is_array:
        return values
    if len(values) == 1:
        return values[0]
    if not values:
        return None
    if strict:
        raise frame.error(f"scalar <{frame.tag} name={frame.attrs.get('name')!r}> has {len(values)} start values")
    return values


class _VariableBuilder(Builder[VariableFields]):
    """Builds one variable element into its class and constructor arguments."""

    __slots__ = ("_attrs", "_cls", "_start_children")

    def __init__(self, cls: type[AbstractVariable], attrs: AttrTable, *, start_children: bool = False) -> None:
        self._cls = cls
        self._attrs = attrs
        self._start_children = start_children

    def __call__(self, frame: Frame, /, *, strict: bool) -> VariableFields:
        """Merge attributes and children into the variable's fields."""
        fields = attributes(frame, self._attrs, strict=strict)
        if "variability" not in fields:
            causality = fields.get("causality", Causality.LOCAL)
            fields["variability"] = default_variability(frame.tag, str(getattr(causality, "value", causality)))
        aliases = frame.all("Alias")
        if aliases:
            fields["aliases"] = tuple(aliases)
        if self._cls is ClockVariable:
            return self._cls, fields
        dimensions = tuple(frame.all("Dimension"))
        if dimensions:
            fields["dimensions"] = dimensions
        starts = tuple(frame.all("Start")) if self._start_children else fields.pop("start", ())
        start = _shape_start(frame, starts, is_array=bool(dimensions), strict=strict)
        if start is not None:
            fields["start"] = start
        return self._cls, fields


def _variable_grammar(tag: str, builder: _VariableBuilder, start_attrs: AttrTable | None) -> Grammar[VariableFields]:
    children: dict[str, ChildRule] = {"Annotations": SKIP}
    alias_attrs = FLOAT_ALIAS_ATTRS if tag in _FLOAT_ELEMENTS else ALIAS_ATTRS
    children["Alias"] = _Part(Alias, alias_attrs)
    if tag != "Clock":
        children["Dimension"] = _Part(Dimension, DIMENSION_ATTRS)
    if start_attrs is not None:
        children["Start"] = _StartValue(start_attrs)
    return Grammar(root=tag, stop_at="", build_root=builder, children={tag: children})


def _grammars() -> Mapping[str, Grammar[VariableFields]]:
    integer_kinds: dict[str, tuple[type[AbstractVariable], c.IntRange]] = {
        "Int8": (Int8Variable, c.BYTE),
        "UInt8": (UInt8Variable, c.UNSIGNED_BYTE),
        "Int16": (Int16Variable, c.SHORT),
        "UInt16": (UInt16Variable, c.UNSIGNED_SHORT),
        "Int32": (Int32Variable, c.INT),
        "UInt32": (UInt32Variable, c.UNSIGNED_INT),
        "Int64": (Int64Variable, c.LONG),
        "UInt64": (UInt64Variable, c.UNSIGNED_LONG),
    }
    float_attrs = _float_attrs()
    builders: dict[str, tuple[_VariableBuilder, AttrTable | None]] = {
        "Float32": (_VariableBuilder(Float32Variable, float_attrs), None),
        "Float64": (_VariableBuilder(Float64Variable, float_attrs), None),
        **{tag: (_VariableBuilder(cls, _integer_attrs(bounds)), None) for tag, (cls, bounds) in integer_kinds.items()},
        "Boolean": (_VariableBuilder(BooleanVariable, BOOLEAN_ATTRS), None),
        "String": (_VariableBuilder(StringVariable, STRING_ATTRS, start_children=True), STRING_START_ATTRS),
        "Binary": (_VariableBuilder(BinaryVariable, BINARY_ATTRS, start_children=True), BINARY_START_ATTRS),
        "Enumeration": (_VariableBuilder(EnumerationVariable, ENUMERATION_ATTRS), None),
        "Clock": (_VariableBuilder(ClockVariable, CLOCK_ATTRS), None),
    }
    return MappingProxyType(
        {tag: _variable_grammar(tag, builder, start_attrs) for tag, (builder, start_attrs) in builders.items()}
    )


VARIABLE_GRAMMARS = _grammars()
"""The grammar for each variable element, keyed by element name."""


def filter_values(element: str, attrs: Mapping[str, str]) -> tuple[str, str]:
    """Return a variable's causality and variability from its raw attributes, with defaults applied."""
    causality = attrs.get("causality", Causality.LOCAL.value).strip()
    variability = attrs.get("variability")
    if variability is None:
        return causality, default_variability(element, causality).value
    return causality, variability.strip()
