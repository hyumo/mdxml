"""The FMI 3.0 Model Header: everything in ``fmiModelDescription`` before ``ModelVariables``.

Classes mirror the FMI 3.0 XSD (``schema/fmi3``): one per element, field
names are the XSD attribute names in snake_case, and defaults are the XSD
defaults. ``Annotations`` children, which FMI 3 allows on most elements,
are skipped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType

from mdxml import _convert as c
from mdxml._grammar import SKIP, Builder, ChildRule, Collect, Grammar
from mdxml._lookup import Named
from mdxml._schema import (
    Attr,
    AttrTable,
    Frame,
    attributes,
    double,
    flag,
    required_text,
    table,
    text,
)

# --- Enums ----------------------------------------------------------------------------------


class VariableNamingConvention(str, Enum):
    """``variableNamingConvention`` on ``fmiModelDescription``."""

    FLAT = "flat"
    STRUCTURED = "structured"


class IntervalVariability(str, Enum):
    """``intervalVariability`` of a clock."""

    CONSTANT = "constant"
    FIXED = "fixed"
    TUNABLE = "tunable"
    CHANGING = "changing"
    COUNTDOWN = "countdown"
    TRIGGERED = "triggered"


# --- Interface Types ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelExchange:
    """The ``ModelExchange`` Interface Type."""

    model_identifier: str
    needs_execution_tool: bool = False
    can_be_instantiated_only_once_per_process: bool = False
    can_get_and_set_fmu_state: bool = False
    can_serialize_fmu_state: bool = False
    provides_directional_derivatives: bool = False
    provides_adjoint_derivatives: bool = False
    provides_per_element_dependencies: bool = False
    needs_completed_integrator_step: bool = False
    provides_evaluate_discrete_states: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CoSimulation:
    """The ``CoSimulation`` Interface Type."""

    model_identifier: str
    needs_execution_tool: bool = False
    can_be_instantiated_only_once_per_process: bool = False
    can_get_and_set_fmu_state: bool = False
    can_serialize_fmu_state: bool = False
    provides_directional_derivatives: bool = False
    provides_adjoint_derivatives: bool = False
    provides_per_element_dependencies: bool = False
    can_handle_variable_communication_step_size: bool = False
    fixed_internal_step_size: float | None = None
    max_output_derivative_order: int = 0
    recommended_intermediate_input_smoothness: int = 0
    provides_intermediate_update: bool = False
    might_return_early_from_do_step: bool = False
    can_return_early_after_intermediate_update: bool = False
    has_event_mode: bool = False
    provides_evaluate_discrete_states: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledExecution:
    """The ``ScheduledExecution`` Interface Type."""

    model_identifier: str
    needs_execution_tool: bool = False
    can_be_instantiated_only_once_per_process: bool = False
    can_get_and_set_fmu_state: bool = False
    can_serialize_fmu_state: bool = False
    provides_directional_derivatives: bool = False
    provides_adjoint_derivatives: bool = False
    provides_per_element_dependencies: bool = False


# --- Units ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class BaseUnit:
    """A unit's exponents of the SI base units, plus ``factor`` and ``offset`` to convert to them.

    Field names keep the XSD's case-sensitive SI symbols (``A`` is ampere, ``K`` is kelvin).
    """

    kg: int = 0
    m: int = 0
    s: int = 0
    A: int = 0
    K: int = 0
    mol: int = 0
    cd: int = 0
    rad: int = 0
    factor: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class DisplayUnit:
    """A unit to display values in, converted from the unit by ``factor``, ``offset`` and ``inverse``."""

    name: str
    factor: float = 1.0
    offset: float = 0.0
    inverse: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Unit:
    """A ``Unit`` in ``UnitDefinitions``."""

    name: str
    base_unit: BaseUnit | None = None
    display_units: tuple[DisplayUnit, ...] = ()


# --- Type definitions -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class _FloatType:
    name: str
    description: str | None = None
    quantity: str | None = None
    unit: str | None = None
    display_unit: str | None = None
    relative_quantity: bool = False
    unbounded: bool = False
    min: float | None = None
    max: float | None = None
    nominal: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Float32Type(_FloatType):
    """A ``Float32Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Float64Type(_FloatType):
    """A ``Float64Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class _IntegerType:
    name: str
    description: str | None = None
    quantity: str | None = None
    min: int | None = None
    max: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Int8Type(_IntegerType):
    """An ``Int8Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt8Type(_IntegerType):
    """A ``UInt8Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Int16Type(_IntegerType):
    """An ``Int16Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt16Type(_IntegerType):
    """A ``UInt16Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Int32Type(_IntegerType):
    """An ``Int32Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt32Type(_IntegerType):
    """A ``UInt32Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Int64Type(_IntegerType):
    """An ``Int64Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class UInt64Type(_IntegerType):
    """A ``UInt64Type`` type definition."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BooleanType:
    """A ``BooleanType`` type definition."""

    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StringType:
    """A ``StringType`` type definition."""

    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BinaryType:
    """A ``BinaryType`` type definition."""

    name: str
    description: str | None = None
    mime_type: str = "application/octet-stream"
    max_size: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Item:
    """One allowed value of an ``EnumerationType``."""

    name: str
    value: int
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EnumerationType:
    """An ``EnumerationType`` type definition."""

    name: str
    description: str | None = None
    quantity: str | None = None
    min: int | None = None
    max: int | None = None
    items: tuple[Item, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ClockType:
    """A ``ClockType`` type definition."""

    name: str
    interval_variability: IntervalVariability | str
    description: str | None = None
    can_be_deactivated: bool = False
    priority: int | None = None
    interval_decimal: float | None = None
    shift_decimal: float = 0.0
    supports_fraction: bool = False
    resolution: int | None = None
    interval_counter: int | None = None
    shift_counter: int = 0


TypeDefinition = (
    Float32Type
    | Float64Type
    | Int8Type
    | UInt8Type
    | Int16Type
    | UInt16Type
    | Int32Type
    | UInt32Type
    | Int64Type
    | UInt64Type
    | BooleanType
    | StringType
    | BinaryType
    | EnumerationType
    | ClockType
)
"""Any type definition in ``TypeDefinitions``."""


# --- Log categories and default experiment --------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class Category:
    """A log category in ``LogCategories``."""

    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DefaultExperiment:
    """Default simulation settings suggested by the FMU."""

    start_time: float | None = None
    stop_time: float | None = None
    tolerance: float | None = None
    step_size: float | None = None


# --- Model Header ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelHeader:
    """Everything in an FMI 3.0 Model Description before ``ModelVariables``.

    Annotations aren't part of the Model Header.
    """

    fmi_version: str
    model_name: str
    instantiation_token: str
    description: str | None = None
    author: str | None = None
    version: str | None = None
    copyright: str | None = None
    license: str | None = None
    generation_tool: str | None = None
    generation_date_and_time: datetime | None = None
    variable_naming_convention: VariableNamingConvention | str = VariableNamingConvention.FLAT
    model_exchange: ModelExchange | None = None
    co_simulation: CoSimulation | None = None
    scheduled_execution: ScheduledExecution | None = None
    unit_definitions: Named[Unit] = field(default_factory=Named)
    type_definitions: Named[TypeDefinition] = field(default_factory=Named)
    log_categories: Named[Category] = field(default_factory=Named)
    default_experiment: DefaultExperiment | None = None

    def __post_init__(self) -> None:
        """Accept plain tuples for the definition lists, so headers can be built by hand."""
        for name in ("unit_definitions", "type_definitions", "log_categories"):
            value = getattr(self, name)
            if not isinstance(value, Named):
                object.__setattr__(self, name, Named(value))


# --- Attribute tables -----------------------------------------------------------------------

FMI_VERSION_PATTERN = re.compile(r"3[.](0|[1-9][0-9]*)([.](0|[1-9][0-9]*))?(-.+)?")


def _fmi_version(value: str, *, strict: bool) -> str:
    """``fmiVersion``: in strict mode it must match the FMI 3 XSD's pattern."""
    if strict and not FMI_VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"{value!r} doesn't match the FMI 3 version pattern")
    return value


ROOT_ATTRS = table(
    Attr("fmiVersion", "fmi_version", _fmi_version, required=True, fallback=""),
    required_text("modelName", "model_name"),
    required_text("instantiationToken", "instantiation_token"),
    text("description", "description"),
    text("author", "author"),
    text("version", "version"),
    text("copyright", "copyright"),
    text("license", "license"),
    text("generationTool", "generation_tool"),
    Attr("generationDateAndTime", "generation_date_and_time", c.to_datetime),
    Attr("variableNamingConvention", "variable_naming_convention", c.EnumConverter(VariableNamingConvention)),
)

_INTERFACE_ATTRS = (
    required_text("modelIdentifier", "model_identifier"),
    flag("needsExecutionTool", "needs_execution_tool"),
    flag("canBeInstantiatedOnlyOncePerProcess", "can_be_instantiated_only_once_per_process"),
    flag("canGetAndSetFMUState", "can_get_and_set_fmu_state"),
    flag("canSerializeFMUState", "can_serialize_fmu_state"),
    flag("providesDirectionalDerivatives", "provides_directional_derivatives"),
    flag("providesAdjointDerivatives", "provides_adjoint_derivatives"),
    flag("providesPerElementDependencies", "provides_per_element_dependencies"),
)

MODEL_EXCHANGE_ATTRS = table(
    *_INTERFACE_ATTRS,
    flag("needsCompletedIntegratorStep", "needs_completed_integrator_step"),
    flag("providesEvaluateDiscreteStates", "provides_evaluate_discrete_states"),
)

CO_SIMULATION_ATTRS = table(
    *_INTERFACE_ATTRS,
    flag("canHandleVariableCommunicationStepSize", "can_handle_variable_communication_step_size"),
    double("fixedInternalStepSize", "fixed_internal_step_size"),
    Attr("maxOutputDerivativeOrder", "max_output_derivative_order", c.UNSIGNED_INT),
    Attr("recommendedIntermediateInputSmoothness", "recommended_intermediate_input_smoothness", c.INT),
    flag("providesIntermediateUpdate", "provides_intermediate_update"),
    flag("mightReturnEarlyFromDoStep", "might_return_early_from_do_step"),
    flag("canReturnEarlyAfterIntermediateUpdate", "can_return_early_after_intermediate_update"),
    flag("hasEventMode", "has_event_mode"),
    flag("providesEvaluateDiscreteStates", "provides_evaluate_discrete_states"),
)

SCHEDULED_EXECUTION_ATTRS = table(*_INTERFACE_ATTRS)

UNIT_ATTRS = table(required_text("name", "name"))

BASE_UNIT_ATTRS = table(
    *(Attr(symbol, symbol, c.INT) for symbol in ("kg", "m", "s", "A", "K", "mol", "cd", "rad")),
    double("factor", "factor"),
    double("offset", "offset"),
)

DISPLAY_UNIT_ATTRS = table(
    required_text("name", "name"),
    double("factor", "factor"),
    double("offset", "offset"),
    flag("inverse", "inverse"),
)

_TYPE_BASE_ATTRS = (
    required_text("name", "name"),
    text("description", "description"),
)

FLOAT_TYPE_ATTRS = table(
    *_TYPE_BASE_ATTRS,
    text("quantity", "quantity"),
    text("unit", "unit"),
    text("displayUnit", "display_unit"),
    flag("relativeQuantity", "relative_quantity"),
    flag("unbounded", "unbounded"),
    double("min", "min"),
    double("max", "max"),
    double("nominal", "nominal"),
)


def _integer_type_attrs(bounds: c.IntRange) -> AttrTable:
    return table(
        *_TYPE_BASE_ATTRS,
        text("quantity", "quantity"),
        Attr("min", "min", bounds),
        Attr("max", "max", bounds),
    )


PLAIN_TYPE_ATTRS = table(*_TYPE_BASE_ATTRS)

BINARY_TYPE_ATTRS = table(
    *_TYPE_BASE_ATTRS,
    text("mimeType", "mime_type"),
    Attr("maxSize", "max_size", c.to_unsigned_int),  # xs:nonNegativeInteger has no upper bound
)

ENUMERATION_TYPE_ATTRS = table(
    *_TYPE_BASE_ATTRS,
    text("quantity", "quantity"),
    Attr("min", "min", c.LONG),
    Attr("max", "max", c.LONG),
)

ITEM_ATTRS = table(
    required_text("name", "name"),
    Attr("value", "value", c.LONG, required=True),
    text("description", "description"),
)

CLOCK_TYPE_ATTRS = table(
    *_TYPE_BASE_ATTRS,
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

CATEGORY_ATTRS = table(
    required_text("name", "name"),
    text("description", "description"),
)

DEFAULT_EXPERIMENT_ATTRS = table(
    double("startTime", "start_time"),
    double("stopTime", "stop_time"),
    double("tolerance", "tolerance"),
    double("stepSize", "step_size"),
)


# --- Builders -------------------------------------------------------------------------------


class _Simple(Builder[object]):
    """Builds ``cls`` from the element's attributes alone."""

    __slots__ = ("_attrs", "_cls")

    def __init__(self, cls: type[object], attrs: AttrTable) -> None:
        self._cls = cls
        self._attrs = attrs

    def __call__(self, frame: Frame, /, *, strict: bool) -> object:
        """Build the object."""
        return self._cls(**attributes(frame, self._attrs, strict=strict))


def _build_unit(frame: Frame, *, strict: bool) -> Unit:
    return Unit(
        **attributes(frame, UNIT_ATTRS, strict=strict),
        base_unit=frame.one("BaseUnit", strict=strict),
        display_units=tuple(frame.all("DisplayUnit")),
    )


def _build_enumeration_type(frame: Frame, *, strict: bool) -> EnumerationType:
    return EnumerationType(
        **attributes(frame, ENUMERATION_TYPE_ATTRS, strict=strict),
        items=tuple(frame.all("Item")),
    )


def build_header(frame: Frame, *, strict: bool) -> ModelHeader:
    """Build the :class:`ModelHeader` from the root element and the children read so far."""
    return ModelHeader(
        **attributes(frame, ROOT_ATTRS, strict=strict),
        model_exchange=frame.one("ModelExchange", strict=strict),
        co_simulation=frame.one("CoSimulation", strict=strict),
        scheduled_execution=frame.one("ScheduledExecution", strict=strict),
        unit_definitions=Named(frame.one("UnitDefinitions", strict=strict) or ()),
        type_definitions=Named(frame.one("TypeDefinitions", strict=strict) or ()),
        log_categories=Named(frame.one("LogCategories", strict=strict) or ()),
        default_experiment=frame.one("DefaultExperiment", strict=strict),
    )


TYPE_DEFINITIONS: Mapping[str, tuple[type[TypeDefinition], AttrTable]] = MappingProxyType(
    {
        "Float32Type": (Float32Type, FLOAT_TYPE_ATTRS),
        "Float64Type": (Float64Type, FLOAT_TYPE_ATTRS),
        "Int8Type": (Int8Type, _integer_type_attrs(c.BYTE)),
        "UInt8Type": (UInt8Type, _integer_type_attrs(c.UNSIGNED_BYTE)),
        "Int16Type": (Int16Type, _integer_type_attrs(c.SHORT)),
        "UInt16Type": (UInt16Type, _integer_type_attrs(c.UNSIGNED_SHORT)),
        "Int32Type": (Int32Type, _integer_type_attrs(c.INT)),
        "UInt32Type": (UInt32Type, _integer_type_attrs(c.UNSIGNED_INT)),
        "Int64Type": (Int64Type, _integer_type_attrs(c.LONG)),
        "UInt64Type": (UInt64Type, _integer_type_attrs(c.UNSIGNED_LONG)),
        "BooleanType": (BooleanType, PLAIN_TYPE_ATTRS),
        "StringType": (StringType, PLAIN_TYPE_ATTRS),
        "BinaryType": (BinaryType, BINARY_TYPE_ATTRS),
        "EnumerationType": (EnumerationType, ENUMERATION_TYPE_ATTRS),
        "ClockType": (ClockType, CLOCK_TYPE_ATTRS),
    }
)
"""Each type definition element's class and attribute table."""

_TYPE_BUILDERS: Mapping[str, ChildRule] = MappingProxyType(
    {
        tag: _build_enumeration_type if tag == "EnumerationType" else _Simple(cls, attrs)
        for tag, (cls, attrs) in TYPE_DEFINITIONS.items()
    }
)

# Elements that may hold an <Annotations> child, which is skipped.
_ANNOTATABLE = (
    "ModelExchange",
    "CoSimulation",
    "ScheduledExecution",
    "Unit",
    "DisplayUnit",
    *_TYPE_BUILDERS,
    "Item",
    "Category",
    "DefaultExperiment",
)


def _header_children() -> dict[str, dict[str, ChildRule]]:
    """Return which children each header element may contain; ``Annotations`` are skipped everywhere."""
    children: dict[str, dict[str, ChildRule]] = {
        "fmiModelDescription": {
            "ModelExchange": _Simple(ModelExchange, MODEL_EXCHANGE_ATTRS),
            "CoSimulation": _Simple(CoSimulation, CO_SIMULATION_ATTRS),
            "ScheduledExecution": _Simple(ScheduledExecution, SCHEDULED_EXECUTION_ATTRS),
            "UnitDefinitions": Collect("Unit"),
            "TypeDefinitions": Collect(),
            "LogCategories": Collect("Category"),
            "DefaultExperiment": _Simple(DefaultExperiment, DEFAULT_EXPERIMENT_ATTRS),
        },
        "UnitDefinitions": {"Unit": _build_unit},
        "Unit": {
            "BaseUnit": _Simple(BaseUnit, BASE_UNIT_ATTRS),
            "DisplayUnit": _Simple(DisplayUnit, DISPLAY_UNIT_ATTRS),
        },
        "TypeDefinitions": dict(_TYPE_BUILDERS),
        "EnumerationType": {"Item": _Simple(Item, ITEM_ATTRS)},
        "LogCategories": {"Category": _Simple(Category, CATEGORY_ATTRS)},
    }
    for parent in _ANNOTATABLE:
        children.setdefault(parent, {})["Annotations"] = SKIP
    return children


HEADER_GRAMMAR = Grammar(
    root="fmiModelDescription",
    stop_at="ModelVariables",
    build_root=build_header,
    children=_header_children(),
)
