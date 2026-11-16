"""FMI 2.0 Model Variables: the ``ScalarVariable`` elements in ``ModelVariables``.

Each ``ScalarVariable`` holds exactly one typed child (``Real``, ``Integer``,
``Boolean``, ``String`` or ``Enumeration``). Its attributes are merged into
one object per variable, of the class for that kind; ``type_name`` says which.
Every variable also gets its Variable Index: its 1-based position in
``ModelVariables``, which FMI 2's Model Structure uses to refer to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, cast

from mdxml import _convert as c
from mdxml._grammar import SKIP, Grammar
from mdxml._schema import Attr, AttrTable, Frame, attributes, double, flag, required_text, table, text

# --- Enums ----------------------------------------------------------------------------------


class Causality(str, Enum):
    """``causality`` of a ScalarVariable."""

    PARAMETER = "parameter"
    CALCULATED_PARAMETER = "calculatedParameter"
    INPUT = "input"
    OUTPUT = "output"
    LOCAL = "local"
    INDEPENDENT = "independent"


class Variability(str, Enum):
    """``variability`` of a ScalarVariable."""

    CONSTANT = "constant"
    FIXED = "fixed"
    TUNABLE = "tunable"
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"


class Initial(str, Enum):
    """``initial`` of a ScalarVariable."""

    EXACT = "exact"
    APPROX = "approx"
    CALCULATED = "calculated"


# The FMI 2.0 standard's table of causality x variability (section 2.2.7): the default
# `initial` for each valid combination, or None where `initial` isn't allowed (inputs and
# the independent variable). Combinations not listed are invalid and have no default.
_DEFAULT_INITIAL: Mapping[tuple[Causality, Variability], Initial | None] = MappingProxyType(
    {
        # Case A, where only "exact" is allowed.
        (Causality.OUTPUT, Variability.CONSTANT): Initial.EXACT,
        (Causality.LOCAL, Variability.CONSTANT): Initial.EXACT,
        (Causality.PARAMETER, Variability.FIXED): Initial.EXACT,
        (Causality.PARAMETER, Variability.TUNABLE): Initial.EXACT,
        # Case B, where "calculated" (the default) or "approx" is allowed.
        (Causality.CALCULATED_PARAMETER, Variability.FIXED): Initial.CALCULATED,
        (Causality.CALCULATED_PARAMETER, Variability.TUNABLE): Initial.CALCULATED,
        (Causality.LOCAL, Variability.FIXED): Initial.CALCULATED,
        (Causality.LOCAL, Variability.TUNABLE): Initial.CALCULATED,
        # Case C, where "calculated" (the default), "exact" or "approx" is allowed.
        (Causality.OUTPUT, Variability.DISCRETE): Initial.CALCULATED,
        (Causality.OUTPUT, Variability.CONTINUOUS): Initial.CALCULATED,
        (Causality.LOCAL, Variability.DISCRETE): Initial.CALCULATED,
        (Causality.LOCAL, Variability.CONTINUOUS): Initial.CALCULATED,
        # Case D, inputs, which have no initial.
        (Causality.INPUT, Variability.DISCRETE): None,
        (Causality.INPUT, Variability.CONTINUOUS): None,
        # Case E, the independent variable, which has no initial.
        (Causality.INDEPENDENT, Variability.CONTINUOUS): None,
    }
)


def default_initial(causality: Causality | str, variability: Variability | str) -> Initial | None:
    """Return the FMI 2.0 standard's default ``initial`` for a causality and variability.

    ``None`` when ``initial`` isn't allowed for the combination, when the
    combination is invalid, or when either value isn't a known enum value.
    """
    if not isinstance(causality, Causality) or not isinstance(variability, Variability):
        return None
    return _DEFAULT_INITIAL.get((causality, variability))


# --- Variables ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ScalarVariable:
    """Attributes every FMI 2.0 Model Variable has, whatever its kind."""

    name: str
    value_reference: int
    index: int
    """The Variable Index: 1-based position in ``ModelVariables``."""
    description: str | None = None
    causality: Causality | str = Causality.LOCAL
    variability: Variability | str = Variability.CONTINUOUS
    initial: Initial | str | None = None
    """``initial`` exactly as written; see :attr:`effective_initial`."""
    can_handle_multiple_set_per_time_instant: bool | None = None
    declared_type: str | None = None

    @property
    def effective_initial(self) -> Initial | str | None:
        """``initial`` as written, or else the standard's default for this causality and variability."""
        if self.initial is not None:
            return self.initial
        return default_initial(self.causality, self.variability)


@dataclass(frozen=True, slots=True, kw_only=True)
class RealVariable(ScalarVariable):
    """A ScalarVariable with a ``Real`` element."""

    type_name: str = field(default="Real", init=False)
    quantity: str | None = None
    unit: str | None = None
    display_unit: str | None = None
    relative_quantity: bool = False
    min: float | None = None
    max: float | None = None
    nominal: float | None = None
    unbounded: bool = False
    start: float | None = None
    derivative: int | None = None
    """Variable Index of the state this variable is the derivative of."""
    reinit: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class IntegerVariable(ScalarVariable):
    """A ScalarVariable with an ``Integer`` element."""

    type_name: str = field(default="Integer", init=False)
    quantity: str | None = None
    min: int | None = None
    max: int | None = None
    start: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BooleanVariable(ScalarVariable):
    """A ScalarVariable with a ``Boolean`` element."""

    type_name: str = field(default="Boolean", init=False)
    start: bool | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StringVariable(ScalarVariable):
    """A ScalarVariable with a ``String`` element."""

    type_name: str = field(default="String", init=False)
    start: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EnumerationVariable(ScalarVariable):
    """A ScalarVariable with an ``Enumeration`` element. ``declared_type`` names its EnumerationType."""

    type_name: str = field(default="Enumeration", init=False)
    quantity: str | None = None
    min: int | None = None
    max: int | None = None
    start: int | None = None


Variable = RealVariable | IntegerVariable | BooleanVariable | StringVariable | EnumerationVariable
"""Any FMI 2.0 Model Variable."""


# --- Attribute tables -----------------------------------------------------------------------

SCALAR_VARIABLE_ATTRS = table(
    required_text("name", "name"),
    Attr("valueReference", "value_reference", c.UNSIGNED_INT, required=True),
    text("description", "description"),
    Attr("causality", "causality", c.EnumConverter(Causality)),
    Attr("variability", "variability", c.EnumConverter(Variability)),
    Attr("initial", "initial", c.EnumConverter(Initial)),
    flag("canHandleMultipleSetPerTimeInstant", "can_handle_multiple_set_per_time_instant"),
)

REAL_ATTRS = table(
    text("declaredType", "declared_type"),
    text("quantity", "quantity"),
    text("unit", "unit"),
    text("displayUnit", "display_unit"),
    flag("relativeQuantity", "relative_quantity"),
    double("min", "min"),
    double("max", "max"),
    double("nominal", "nominal"),
    flag("unbounded", "unbounded"),
    double("start", "start"),
    Attr("derivative", "derivative", c.UNSIGNED_INT),
    flag("reinit", "reinit"),
)

INTEGER_ATTRS = table(
    text("declaredType", "declared_type"),
    text("quantity", "quantity"),
    Attr("min", "min", c.INT),
    Attr("max", "max", c.INT),
    Attr("start", "start", c.INT),
)

BOOLEAN_ATTRS = table(
    text("declaredType", "declared_type"),
    flag("start", "start"),
)

STRING_ATTRS = table(
    text("declaredType", "declared_type"),
    text("start", "start"),
)

ENUMERATION_ATTRS = table(
    required_text("declaredType", "declared_type"),
    text("quantity", "quantity"),
    Attr("min", "min", c.INT),
    Attr("max", "max", c.INT),
    Attr("start", "start", c.INT),
)

_KINDS: Mapping[str, tuple[type[ScalarVariable], AttrTable]] = MappingProxyType(
    {
        "Real": (RealVariable, REAL_ATTRS),
        "Integer": (IntegerVariable, INTEGER_ATTRS),
        "Boolean": (BooleanVariable, BOOLEAN_ATTRS),
        "String": (StringVariable, STRING_ATTRS),
        "Enumeration": (EnumerationVariable, ENUMERATION_ATTRS),
    }
)

VariableFields = tuple[type[ScalarVariable], dict[str, Any]]
"""A variable's class and constructor arguments, everything but its Variable Index."""


# --- Builders -------------------------------------------------------------------------------


class _Kind:
    """Builds a typed child (e.g. ``<Real>``) into its variable class and attributes."""

    __slots__ = ("_attrs", "_cls")

    def __init__(self, tag: str) -> None:
        self._cls, self._attrs = _KINDS[tag]

    def __call__(self, frame: Frame, /, *, strict: bool) -> VariableFields:
        """Return the class and the typed child's attributes."""
        return self._cls, attributes(frame, self._attrs, strict=strict)


def build_scalar_variable(frame: Frame, *, strict: bool) -> VariableFields:
    """Merge a ``ScalarVariable``'s attributes with its typed child's."""
    common = attributes(frame, SCALAR_VARIABLE_ATTRS, strict=strict)
    kinds = [obj for tag, obj in frame.children if tag in _KINDS]
    if not kinds:
        raise frame.error(
            f"<ScalarVariable name={common['name']!r}> has no Real, Integer, Boolean, String or Enumeration"
        )
    if len(kinds) > 1 and strict:
        raise frame.error(f"<ScalarVariable name={common['name']!r}> has {len(kinds)} type elements, expected one")
    cls, kind_fields = cast("VariableFields", kinds[0])
    return cls, {**common, **kind_fields}


VARIABLE_GRAMMAR = Grammar(
    root="ScalarVariable",
    stop_at="",  # a ScalarVariable is always read whole
    build_root=build_scalar_variable,
    children={
        "ScalarVariable": {**{tag: _Kind(tag) for tag in _KINDS}, "Annotations": SKIP},
    },
)

VARIABLE_GRAMMARS: Mapping[str, Grammar[VariableFields]] = MappingProxyType({"ScalarVariable": VARIABLE_GRAMMAR})
"""The grammar for each variable element, keyed by element name."""


def filter_values(element: str, attrs: Mapping[str, str]) -> tuple[str, str]:
    """Return a variable's causality and variability from its raw attributes, with XSD defaults applied."""
    return (
        attrs.get("causality", Causality.LOCAL.value).strip(),
        attrs.get("variability", Variability.CONTINUOUS.value).strip(),
    )
